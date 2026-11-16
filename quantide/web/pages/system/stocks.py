"""系统维护 - 股票列表模块"""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Div,
    Span,
    Td,
    Tr,
)
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    H2,
    Input,
    UkIcon,
)
from starlette.requests import Request

from quantide.data.models.stocks import stock_list
from quantide.web.application import fast_app
from quantide.web.components.data_tables import (
    DatasetPagination,
    DatasetTable,
    pagination_button_class,
)
from quantide.web.components.system import subtle_icon_button
from quantide.web.layouts.main import MainLayout
from quantide.web.theme import PRIMARY_COLOR, AppTheme

# 定义子路由应用
system_stocks_app, rt = fast_app(hdrs=AppTheme.headers())


def _append_security_table_rows(data: Sequence[Mapping[Any, Any]], rows: list[Any]) -> None:
    """Append security table rows."""
    if data:
        for row in data:
            list_date_str = (
                str(row.get("list_date", "")).split(" ")[0] if row.get("list_date") else ""
            )
            delist_date_str = ""
            if row.get("delist_date") and str(row.get("delist_date")) != "NaT":
                delist_date_str = str(row.get("delist_date")).split(" ")[0]

            delist_info = ""
            if delist_date_str:
                delist_info = Span(f" (退市: {delist_date_str})", cls="text-xs text-red-400")

            rows.append(
                Tr(
                    Td(row.get("asset", ""), cls="px-4 py-2 text-sm text-gray-900"),
                    Td(
                        Span(row.get("name", "")),
                        delist_info,
                        cls="px-4 py-2 text-sm text-gray-900",
                    ),
                    Td(row.get("pinyin", ""), cls="px-4 py-2 text-sm text-gray-500"),
                    Td(list_date_str, cls="px-4 py-2 text-sm text-gray-500"),
                    cls="hover:bg-gray-50",
                )
            )
    else:
        rows.append(Tr(Td("暂无数据", colspan="4", cls="px-4 py-8 text-center text-gray-500")))


def _build_stock_table(
    data: Sequence[Mapping[Any, Any]],
    page: int = 1,
    per_page: int = 20,
    total: int = 0,
    query: str = "",
) -> Any:
    """构建股票列表表格"""
    rows: list[Any] = []
    _append_security_table_rows(data, rows)

    total_pages = max(1, (total + per_page - 1) // per_page) if total > 0 else 1
    pagination_info = (
        f"显示第 {(page - 1) * per_page + 1} 到 {min(page * per_page, total)} 条，共 {total} 条"
        if total > 0
        else "暂无数据"
    )

    def page_url(p: int, pp: int = per_page) -> str:
        return f"/system/stocks/?page={p}&per_page={pp}&q={query}"

    return Div(
        DatasetTable(["代码", "名称", "拼音", "上市日期"], rows),
        DatasetPagination(
            pagination_info,
            page,
            per_page,
            total_pages,
            page_url,
            pagination_button_class,
        ),
        cls="bg-white rounded-lg shadow overflow-hidden",
    )


@rt("/")
async def index(req: Request, page: int = 1, per_page: int = 20, q: str = "") -> Any:
    """股票列表页面"""
    query = q or req.query_params.get("q", "")
    page = int(req.query_params.get("page", page))
    per_page = int(req.query_params.get("per_page", per_page))

    logger.info(f"stocks_page called with query='{query}', page={page}, per_page={per_page}")

    try:
        if query:
            result_df = stock_list.fuzzy_search(query, id_only=False)
            if isinstance(result_df, list):
                raise TypeError("Expected stock search dataframe")
            total = len(result_df)
            if total > 0:
                data = result_df.to_dict("records")
            else:
                data = []
        else:
            df = stock_list.data
            if df is not None:
                total = len(df)
                start_idx = (page - 1) * per_page
                end_idx = min(start_idx + per_page, total)
                data = df.slice(start_idx, end_idx - start_idx).to_pandas().to_dict("records")
            else:
                total = 0
                data = []
    except Exception as e:
        logger.error(f"获取股票列表失败: {e}")
        total = 0
        data = []

    layout = MainLayout(title="股票列表")
    layout.set_sidebar_active("/system/stocks")

    page_content = Div(
        Div(
            Div(
                UkIcon("list", size=32, cls="mr-3", style=f"color: {PRIMARY_COLOR};"),
                H2("股票列表", cls="text-2xl font-bold"),
                cls="flex items-center",
            ),
            subtle_icon_button(
                UkIcon("refresh-cw", size=16),
                post_url="/system/stocks/sync",
                target="#stocks-content",
                label="立即更新股票列表",
            ),
            cls="mb-6 flex items-center justify-between",
        ),
        Div(
            Input(
                type="text",
                name="q",
                value=query,
                placeholder="输入代码、名称或拼音搜索...",
                cls="input input-bordered w-full",
                hx_get="/system/stocks/search",
                hx_trigger="keyup changed delay:200ms, search",
                hx_target="#stocks-content",
                hx_swap="innerHTML",
                hx_include="[name='per_page']",
                hx_vals='{"page": "1"}',
            ),
            Input(type="hidden", name="per_page", value=str(per_page)),
            cls="mb-4",
        ),
        Div(_build_stock_table(data, page, per_page, total, query), id="stocks-content"),
        cls="p-8",
    )

    layout.set_main_block(page_content)
    return layout.render(req)


@rt("/sync", methods="post")
async def sync_stocks() -> Any:
    """同步股票列表数据"""
    try:
        await asyncio.to_thread(stock_list.update)
        logger.info(f"Stock list synced: {stock_list.size} records")

        df = stock_list.data
        if df is not None:
            total = len(df)
            data = df.slice(0, 20).to_pandas().to_dict("records")
        else:
            total = 0
            data = []

        return _build_stock_table(data, 1, 20, total, "")
    except Exception as e:
        logger.error(f"同步股票列表失败: {e}")
        return Div(
            UkIcon("alert-circle", cls="text-red-500 mr-2"),
            f"同步失败: {str(e)}",
            cls="flex items-center p-4 bg-red-50 text-red-700 rounded-lg",
        )


@rt("/search")
async def search(req: Request, q: str = "", per_page: int = 20) -> Any:
    """HTMX 搜索 API，返回表格内容。

    用于防抖自动搜索，仅返回表格部分。
    """
    query = q.strip()
    per_page = int(req.query_params.get("per_page", per_page))
    page = int(req.query_params.get("page", 1))

    logger.info(f"search called with query='{query}', page={page}, per_page={per_page}")

    try:
        if query:
            result_df = stock_list.fuzzy_search(query, id_only=False)
            if isinstance(result_df, list):
                raise TypeError("Expected stock search dataframe")
            total = len(result_df)
            if total > 0:
                # 搜索结果分页
                start_idx = (page - 1) * per_page
                end_idx = min(start_idx + per_page, total)
                data = result_df.iloc[start_idx:end_idx].to_dict("records")
            else:
                data = []
        else:
            df = stock_list.data
            if df is not None:
                total = len(df)
                start_idx = (page - 1) * per_page
                end_idx = min(start_idx + per_page, total)
                data = df.slice(start_idx, end_idx - start_idx).to_pandas().to_dict("records")
            else:
                total = 0
                data = []
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        total = 0
        data = []

    return _build_stock_table(data, page, per_page, total, query)
