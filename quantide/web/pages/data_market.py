"""行情数据管理页面"""

import asyncio
import datetime
from collections.abc import Mapping, Sequence
from typing import Any, cast

from fasthtml.common import *
from fasthtml.common import (
    H3,
    A,
    Button,
    Card,
    Div,
    Form,
    Input,
    P,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)

# Use FastHTML's plain Label for form elements to avoid MonsterUI's uk-label styling
from fasthtml.common import Label as _Label
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    CardBody,
    UkIcon,
)
from starlette.requests import Request

from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.sync_task import DataSyncTask
from quantide.service.background import run_blocking, start_background
from quantide.web.application import fast_app
from quantide.web.components.dataset_pages import (
    DatasetPage,
    DatasetProgressDialog,
    DatasetTabs,
    dataset_progress_response,
    new_sync_status,
)
from quantide.web.theme import AppTheme

# 定义子路由应用
data_market_app, rt = fast_app(hdrs=AppTheme.headers())

# ========== 全局同步状态 ==========
_sync_status = new_sync_status(stage="")


def _get_active_tab(req: Request) -> str:
    return req.query_params.get("tab", "overview")


def _TabNav(active_tab: str) -> Any:
    return DatasetTabs(
        "/data/market",
        active_tab,
        [("overview", "概要"), ("verify", "数据校验"), ("update", "手动补全"), ("browse", "浏览")],
    )


def _OverviewTab() -> Any:
    """概要 Tab 内容"""
    try:
        start_date = daily_bars.start
        end_date = daily_bars.end
        total_dates = daily_bars.total_dates
        size_bytes = daily_bars.size
        # 简单换算 size
        if size_bytes > 1024 * 1024 * 1024:
            size_str = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"

        # 检查是否过期 (简单逻辑：如果结束日期早于上个交易日)
        is_stale = False
        last_trade = calendar.last_trade_date()
        if end_date and last_trade and end_date < last_trade:
            is_stale = True

    except Exception as e:
        return Div(Card(CardBody(P(f"获取行情信息失败: {e}", cls="text-red-500"))))

    return Div(
        H3("日线数据状态", cls="text-xl font-semibold mb-6"),
        Div(
            Div(
                P("数据起始日期", cls="text-sm text-gray-500"),
                P(str(start_date or "--"), cls="text-2xl font-bold"),
                cls="p-4 bg-gray-50 rounded-lg",
            ),
            Div(
                P("数据结束日期", cls="text-sm text-gray-500"),
                P(
                    str(end_date or "--"),
                    cls=f"text-2xl font-bold {'text-red-600' if is_stale else ''}",
                ),
                cls="p-4 bg-gray-50 rounded-lg",
            ),
            Div(
                P("数据天数", cls="text-sm text-gray-500"),
                P(f"{total_dates or 0} 天", cls="text-2xl font-bold"),
                cls="p-4 bg-gray-50 rounded-lg",
            ),
            Div(
                P("存储占用", cls="text-sm text-gray-500"),
                P(size_str, cls="text-2xl font-bold"),
                cls="p-4 bg-gray-50 rounded-lg",
            ),
            cls="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8",
        ),
        A("检查逐标的日线覆盖", href="/data/market?tab=verify", cls="btn btn-outline"),
        cls="animate-in fade-in duration-500",
    )


def _VerifyTab() -> Any:
    """数据校验 Tab 内容"""
    return Div(
        H3("数据一致性校验", cls="text-xl font-semibold mb-4"),
        Div(
            Form(
                Div(
                    Div(
                        _Label("资产 (逗号分隔，可选)", cls="block text-sm font-medium mb-1"),
                        Input(
                            name="assets",
                            placeholder="例如: 000001.SZ, 600000.SH",
                            cls="input w-full",
                        ),
                        cls="flex-1",
                    ),
                    Div(
                        _Label("开始年份", cls="block text-sm font-medium mb-1"),
                        Input(name="start_year", type="number", value="2024", cls="input w-full"),
                        cls="w-32",
                    ),
                    Div(
                        _Label("结束年份", cls="block text-sm font-medium mb-1"),
                        Input(name="end_year", type="number", value="2024", cls="input w-full"),
                        cls="w-32",
                    ),
                    Div(
                        Div(cls="block text-sm mb-1"),
                        Button("手动校验", type="submit", cls="btn btn-primary w-full"),
                        cls="w-32",
                    ),
                    cls="flex gap-4 items-end",
                ),
                hx_post="/data/market/do-verify",
                hx_target="#verify-result",
                hx_indicator="#verify-spinner",
            ),
            cls="p-6 bg-white border rounded-lg shadow-sm mb-6",
        ),
        Div(
            id="verify-spinner",
            cls="htmx-indicator mb-4",
            children=[
                Div(
                    cls="flex items-center text-[#e41815]",
                    children=[UkIcon("loader", cls="animate-spin mr-2"), "正在校验数据，请稍候..."],
                )
            ],
        ),
        Div(id="verify-result"),
        cls="animate-in fade-in duration-500",
    )


def _UpdateTab() -> Any:
    """手动补全 Tab 内容"""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    return Div(
        H3("手动补全行情数据", cls="text-xl font-semibold mb-4"),
        P(
            (
                "指定日期范围进行数据同步：交易日历、证券列表、日线、市值、指数日线与 "
                "PIT 成分。系统会按月批量补全缺失数据，支持断点续传。"
            ),
            cls="text-gray-600 mb-6",
        ),
        Div(
            Form(
                Div(
                    Div(
                        _Label("开始日期", cls="block text-sm font-medium mb-1"),
                        Input(
                            name="start_date", type="date", value="2024-01-01", cls="input w-full"
                        ),
                        cls="flex-1",
                    ),
                    Div(
                        _Label("结束日期", cls="block text-sm font-medium mb-1"),
                        Input(name="end_date", type="date", value=today_str, cls="input w-full"),
                        cls="flex-1",
                    ),
                    Div(
                        _Label("指数代码（可空）", cls="block text-sm font-medium mb-1"),
                        Input(
                            name="index_codes",
                            type="text",
                            value="000300.SH,000905.SH,000852.SH,932000.CSI",
                            cls="input w-full",
                            placeholder="逗号分隔",
                        ),
                        cls="flex-1",
                    ),
                    Div(
                        Div(cls="block text-sm mb-1"),
                        Button(
                            Div(
                                UkIcon("download", cls="mr-2"), "立即更新", cls="flex items-center"
                            ),
                            type="submit",
                            cls="btn btn-primary w-full",
                            id="update-btn",
                            hx_post="/data/market/do-update",
                            hx_target="#update-dialog-container",
                            hx_swap="innerHTML",
                        ),
                        cls="w-32",
                    ),
                    cls="flex gap-4 items-end",
                ),
            ),
            cls="p-6 bg-white border rounded-lg shadow-sm mb-6",
        ),
        Div(id="update-dialog-container"),
        cls="animate-in fade-in duration-500",
    )


def _BrowseTab(req: Request) -> Any:
    """数据浏览 Tab 内容"""
    asset = req.query_params.get("asset", "")
    start = req.query_params.get("start", "")
    end = req.query_params.get("end", "")

    # 默认显示最新 100 条
    df = None
    if asset:
        try:
            # 简单解析日期
            s_dt = (
                datetime.datetime.strptime(start, "%Y-%m-%d").date()
                if start
                else datetime.date(1900, 1, 1)
            )
            e_dt = datetime.datetime.strptime(end, "%Y-%m-%d").date() if end else None
            df = daily_bars.get_bars_in_range(assets=[asset], start=s_dt, end=e_dt, eager_mode=True)
            if not df.is_empty():
                df = df.sort("date", descending=True).head(100)
        except Exception as e:
            logger.error(f"查询行情失败: {e}")

    table_content = P("输入证券代码并点击搜索查看数据...", cls="text-gray-400 text-center py-12")
    if df is not None and not df.is_empty():
        headers = ["日期", "代码", "开盘", "最高", "最低", "收盘", "成交量", "成交额", "复权", "ST"]
        header_row = Tr(*[Th(h) for h in headers])

        rows = []
        for row in df.to_dicts():
            rows.append(
                Tr(
                    Td(
                        str(row["date"].date())
                        if hasattr(row["date"], "date")
                        else str(row["date"])
                    ),
                    Td(row["asset"]),
                    Td(f"{row['open']:.2f}"),
                    Td(f"{row['high']:.2f}"),
                    Td(f"{row['low']:.2f}"),
                    Td(f"{row['close']:.2f}"),
                    Td(f"{row['volume']:.0f}"),
                    Td(f"{row['amount']:.0f}"),
                    Td(f"{row['adjust']:.4f}"),
                    Td(
                        Input(
                            type="checkbox",
                            checked=row.get("is_st", False),
                            disabled=True,
                            cls="checkbox checkbox-sm",
                        )
                    ),
                )
            )
        table_content = Table(
            Thead(header_row), Tbody(*rows), cls="uk-table uk-table-divider uk-table-small text-sm"
        )
    elif asset:
        table_content = P(f"未找到代码 {asset} 的行情数据", cls="text-red-500 text-center py-12")

    return Div(
        H3("行情数据浏览", cls="text-xl font-semibold mb-4"),
        Form(
            Div(
                Input(
                    name="asset",
                    value=asset,
                    placeholder="证券代码 (例如: 000001.SZ)",
                    cls="input flex-1",
                ),
                Input(name="start", value=start, type="date", cls="input w-40"),
                Input(name="end", value=end, type="date", cls="input w-40"),
                Button(UkIcon("search"), type="submit", cls="btn btn-primary"),
                cls="flex gap-2 mb-6",
            ),
            method="GET",
            action="/data/market",
        ),
        Input(type="hidden", name="tab", value="browse"),
        Div(table_content, cls="overflow-x-auto bg-white border rounded-lg"),
        cls="animate-in fade-in duration-500",
    )


@rt("/")
async def index(req: Request) -> Any:
    active_tab = _get_active_tab(req)

    if active_tab == "verify":
        content = _VerifyTab()
    elif active_tab == "update":
        content = _UpdateTab()
    elif active_tab == "browse":
        content = _BrowseTab(req)
    else:
        content = _OverviewTab()

    return DatasetPage(
        req,
        "/data/market",
        "日线行情",
        "bar-chart",
        active_tab,
        [("overview", "概要"), ("verify", "数据校验"), ("update", "手动补全"), ("browse", "浏览")],
        content,
    )


@rt("/do-verify", methods="post")
async def do_verify(form: Mapping[str, object]) -> Any:
    from quantide.service.data_verification import verify_daily_history

    try:
        start = datetime.date(int(cast(str | int, form.get("start_year", 2024))), 1, 1)
        end = datetime.date(int(cast(str | int, form.get("end_year", 2024))), 12, 31)
        assets = [
            value.strip().upper()
            for value in str(form.get("assets") or "").split(",")
            if value.strip()
        ]
        result = await run_blocking(verify_daily_history, start, end, assets)
        problems = result["missing"] + result["invalid"]
        message = (
            f"已校验 {result['assets']} 个标的；缺失交易日 {result['missing']}，"
            f"非法价格/重复行 {result['invalid']}。"
        )
        detail = "；".join(result["examples"])
        if result["missing"]:
            detail += "。缺失可能涉及停牌，需核对数据源；本次未推定停牌。"
        tone = "text-amber-700 bg-amber-50" if problems else "text-green-700 bg-green-50"
        return Div(P(message), P(detail), cls=f"mt-4 p-4 rounded-lg {tone}")
    except Exception as exc:
        return Div(f"校验未完成：{exc}", cls="mt-4 p-4 text-red-700 bg-red-50 rounded-lg")


# ========== SSE 更新逻辑 (复用 init_wizard 模式) ==========


async def _run_market_sync(
    start_date: datetime.date,
    end_date: datetime.date,
    index_codes: Sequence[str] | None = None,
) -> Any:
    global _sync_status
    _sync_status["is_running"] = True
    _sync_status["completed"] = False
    _sync_status["error"] = None
    _sync_status["progress"] = 0
    _sync_status["message"] = "准备同步..."

    try:
        from quantide.service.data_sync import SyncParams, data_sync_service
        from quantide.service.sync_jobs import wait_for_sync

        task = data_sync_service.create_task(
            SyncParams(
                start_date=start_date,
                end_date=end_date,
                index_codes=list(index_codes or []),
            )
        )
        _sync_status["task_id"] = task.task_id
        await wait_for_sync(task.task_id, _market_task_progress, data_sync_service)
        _sync_status.update(progress=100, message="同步完成", completed=True)
    except asyncio.CancelledError:
        _sync_status["error"] = "服务停止，数据任务被中断"
        raise
    except Exception as exc:
        _sync_status["error"] = str(exc)
    finally:
        _sync_status["is_running"] = False


def _market_task_progress(task: DataSyncTask | None) -> None:
    if task is not None:
        _sync_status.update(progress=min(99, task.progress), message=task.message)


@rt("/do-update", methods="post")
async def do_update(req: Request) -> Any:
    form = await req.form()
    start_date_str = form.get("start_date")
    end_date_str = form.get("end_date")

    try:
        if not isinstance(start_date_str, str) or not isinstance(end_date_str, str):
            raise ValueError("Invalid date")
        s_dt = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        e_dt = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except Exception:
        return Div("日期格式不正确", cls="text-red-500")

    index_codes = [
        code.strip() for code in str(form.get("index_codes") or "").split(",") if code.strip()
    ]
    if s_dt > e_dt:
        return Div("开始日期不能晚于结束日期", cls="text-red-500")
    if not _sync_status["is_running"]:
        _sync_status["is_running"] = True
        start_background(_run_market_sync(s_dt, e_dt, index_codes))

    # 返回进度对话框 (简化版)
    return DatasetProgressDialog(
        "market", "数据更新进度", "/data/market/sync-progress", close_id="close-btn"
    )


@rt("/sync-progress")
async def sync_progress() -> Any:
    return dataset_progress_response(_sync_status)
