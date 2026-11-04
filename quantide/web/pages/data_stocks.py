"""股票列表管理页面"""

import asyncio

from fasthtml.common import *
from loguru import logger
from monsterui.all import *

from quantide.data.models.stocks import stock_list
from quantide.service.background import run_blocking, start_background
from quantide.web.application import fast_app
from quantide.web.components.dataset_pages import (
    DatasetPage,
    DatasetProgressDialog,
    DatasetTabs,
    dataset_content,
    dataset_progress_response,
    new_sync_status,
)
from quantide.web.theme import AppTheme

# 定义子路由应用
data_stocks_app, rt = fast_app(hdrs=AppTheme.headers())

# ========== 全局同步状态 ==========
_sync_status = new_sync_status()


def _get_active_tab(req):
    return req.query_params.get("tab", "overview")


def _TabNav(active_tab):
    return DatasetTabs(
        "/data/stocks",
        active_tab,
        [("overview", "概要"), ("search", "查询"), ("update", "手动更新")],
    )


def _OverviewTab():
    """概要 Tab 内容"""
    try:
        total_stocks = stock_list.size
        last_update = stock_list.last_update_time
        file_path = str(stock_list.path)
    except Exception as e:
        return Div(Card(CardBody(P(f"获取股票列表信息失败: {e}", cls="text-red-500"))))

    return Div(
        H3("股票列表概要", cls="text-xl font-semibold mb-6"),
        Div(
            P(Span("共有股票：", cls="font-medium"), f"{total_stocks} 只"),
            P(Span("最后更新：", cls="font-medium"), str(last_update or "从未更新")),
            P(
                Span("文件位置：", cls="font-medium"),
                file_path,
                cls="text-sm text-gray-600 break-all",
            ),
            cls="space-y-4",
        ),
        cls="animate-in fade-in duration-500",
    )


def _SearchTab(req):
    """查询 Tab 内容"""
    q = req.query_params.get("q", "").strip()

    table_content = P(
        "输入关键词开始搜索 (支持代码、名称、拼音)...", cls="text-gray-400 text-center py-12"
    )

    if q:
        try:
            # 使用 fuzzy_search 获取结果
            df = stock_list.fuzzy_search(q, id_only=False)
            if not df.empty:
                headers = ["股票代码", "公司名称", "拼音", "上市日期", "退市日期"]
                header_row = Tr(*[Th(h) for h in headers])

                rows = []
                # 限制显示前 100 条
                for _, row in df.head(100).iterrows():
                    rows.append(
                        Tr(
                            Td(row["asset"], cls="font-mono"),
                            Td(row["name"]),
                            Td(row["pinyin"]),
                            Td(str(row["list_date"])),
                            Td(str(row["delist_date"]) if row["delist_date"] else "None"),
                        )
                    )
                table_content = Table(
                    Thead(header_row),
                    Tbody(*rows),
                    cls="uk-table uk-table-divider uk-table-small text-sm",
                )
            else:
                table_content = P(
                    f"未找到与 '{q}' 匹配的股票", cls="text-red-500 text-center py-12"
                )
        except Exception as e:
            logger.error(f"查询股票失败: {e}")
            table_content = P(f"查询出错: {e}", cls="text-red-500 text-center py-12")

    return Div(
        H3("股票查询", cls="text-xl font-semibold mb-4"),
        Form(
            Div(
                Input(
                    name="q",
                    value=q,
                    placeholder="输入关键词，停顿后自动搜索...",
                    cls="input flex-1",
                    hx_get="/data/stocks?tab=search",
                    hx_trigger="keyup changed delay:500ms",
                    hx_target="#search-results-container",
                    hx_select="#search-results-container",
                ),
                Button(UkIcon("search"), type="submit", cls="btn btn-primary"),
                cls="flex gap-2 mb-6",
            ),
            method="GET",
            action="/data/stocks",
        ),
        Input(type="hidden", name="tab", value="search"),
        Div(
            table_content,
            id="search-results-container",
            cls="overflow-x-auto bg-white border rounded-lg",
        ),
        cls="animate-in fade-in duration-500",
    )


def _UpdateTab():
    """手动更新 Tab 内容"""
    return Div(
        H3("手动更新股票列表", cls="text-xl font-semibold mb-4"),
        P("从 Tushare 同步最新的全市场股票基础信息。", cls="text-gray-600 mb-6"),
        Form(
            Button(
                Div(UkIcon("refresh-cw", cls="mr-2"), "立即更新", cls="flex items-center"),
                type="submit",
                cls="btn btn-primary",
                hx_post="/data/stocks/do-update",
                hx_target="#update-dialog-container",
                hx_swap="innerHTML",
            ),
        ),
        Div(id="update-dialog-container"),
        cls="animate-in fade-in duration-500",
    )


@rt("/")
async def index(req):
    active_tab = _get_active_tab(req)

    content = dataset_content(active_tab, _OverviewTab, _UpdateTab, search=lambda: _SearchTab(req))

    return DatasetPage(
        req,
        "/data/stocks",
        "股票列表",
        "list",
        active_tab,
        [("overview", "概要"), ("search", "查询"), ("update", "手动更新")],
        content,
    )


# ========== SSE 更新逻辑 ==========


async def _run_stocks_sync() -> None:
    global _sync_status
    _sync_status["is_running"] = True
    _sync_status["completed"] = False
    _sync_status["error"] = None
    _sync_status["progress"] = 0
    _sync_status["message"] = "正在获取股票列表..."

    try:
        # stock_list.update 是同步方法
        await run_blocking(stock_list.update)
        _sync_status["progress"] = 100
        _sync_status["message"] = "同步完成"
        _sync_status["completed"] = True
    except asyncio.CancelledError:
        _sync_status["error"] = "服务停止，股票列表同步被中断"
        raise
    except Exception as e:
        logger.error(f"同步股票列表失败: {e}")
        _sync_status["error"] = str(e)
    finally:
        _sync_status["is_running"] = False


@rt("/do-update", methods="post")
async def do_update():
    if not _sync_status["is_running"]:
        _sync_status["is_running"] = True
        start_background(_run_stocks_sync())

    return DatasetProgressDialog("stocks", "股票列表更新进度", "/data/stocks/sync-progress")


@rt("/sync-progress")
async def sync_progress():
    return dataset_progress_response(_sync_status)
