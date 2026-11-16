"""系统维护 - 行情数据模块"""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast
from urllib.parse import urlencode

from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    Form,
    Span,
    Tr,
)
from fasthtml.common import (
    Button as ActionButton,
)
from fasthtml.common import (
    Input as TextInput,
)
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    H2,
    Td,
    UkIcon,
)
from starlette.requests import Request

from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.stocks import stock_list
from quantide.web.application import fast_app
from quantide.web.components.data_tables import (
    DatasetPagination,
    DatasetTable,
    pagination_button_class,
)
from quantide.web.layouts.main import MainLayout
from quantide.web.theme import PRIMARY_COLOR, AppTheme

# 定义子路由应用
system_market_app, rt = fast_app(hdrs=AppTheme.headers())

_FILTER_CONTROL_STYLE = (
    "height:36px;width:144px;min-height:36px;margin:0;box-sizing:border-box;padding:0 12px;"
)


def _parse_flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class _MarketView:
    code: str = ""
    start_date: str = ""
    end_date: str = ""
    adjust: str = "none"
    page: int = 1
    per_page: int = 20
    show_turnover: bool = False
    show_limits: bool = False
    show_st: bool = False

    @classmethod
    def from_request(cls, req: Request) -> _MarketView:
        query = req.query_params
        return cls(
            code=query.get("code", ""),
            start_date=query.get("start_date", ""),
            end_date=query.get("end_date", ""),
            adjust=query.get("adjust") or "none",
            page=int(query.get("page") or 1),
            per_page=int(query.get("per_page") or 20),
            show_turnover=_parse_flag(query.get("show_turnover", "")),
            show_limits=_parse_flag(query.get("show_limits", "")),
            show_st=_parse_flag(query.get("show_st", "")),
        )

    @property
    def show_identity(self) -> bool:
        return not self.code.strip()

    def url(self, *, page: int | None = None, per_page: int | None = None) -> str:
        params = {
            "code": self.code,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "adjust": self.adjust,
            "page": str(self.page if page is None else page),
            "per_page": str(self.per_page if per_page is None else per_page),
        }
        for name in ("show_turnover", "show_limits", "show_st"):
            if getattr(self, name):
                params[name] = "1"
        return f"/system/market/?{urlencode(params)}"


def _state_button_class(active: bool) -> str:
    selected = (
        "bg-white text-[#e41815] border-[#e41815] font-semibold" if active else "border-black/20"
    )
    return f"q-btn q-btn--sm whitespace-nowrap {selected}"


def _display_asset(asset: str) -> str:
    """Drop the exchange suffix in compact market tables."""
    return asset.partition(".")[0]


def _adjust_toggle(state: _MarketView) -> A:
    active = state.adjust == "qfq"
    target = replace(state, adjust="none" if active else "qfq", page=1)
    return A(
        "前复权" if active else "不复权",
        href=target.url(),
        title="切换复权",
        aria_label="切换复权",
        cls=_state_button_class(active),
    )


def _toggle_button(state: _MarketView, show_label: str, hide_label: str, key: str) -> A:
    active = bool(getattr(state, key))
    if key == "show_turnover":
        target = replace(state, show_turnover=not active, page=1)
    elif key == "show_limits":
        target = replace(state, show_limits=not active, page=1)
    elif key == "show_st":
        target = replace(state, show_st=not active, page=1)
    else:
        raise ValueError(f"unknown market toggle: {key}")
    return A(
        hide_label if active else show_label,
        href=target.url(),
        cls=_state_button_class(active),
    )


def _hidden_inputs(state: _MarketView) -> list[Any]:
    inputs: list[Any] = [
        TextInput(type="hidden", name="adjust", value=state.adjust),
        TextInput(type="hidden", name="per_page", value=str(state.per_page)),
    ]
    for name in ("show_turnover", "show_limits", "show_st"):
        if getattr(state, name):
            inputs.append(TextInput(type="hidden", name=name, value="1"))
    return inputs


def _filter_row(state: _MarketView) -> Div:
    return Div(
        Form(
            *_hidden_inputs(state),
            TextInput(
                type="text",
                name="code",
                value=state.code,
                placeholder="证券代码",
                aria_label="证券代码",
                cls="q-input h-9 w-40",
                style=_FILTER_CONTROL_STYLE,
            ),
            TextInput(
                type="date",
                name="start_date",
                value=state.start_date,
                aria_label="起始日期",
                title="起始日期",
                cls="q-input h-9 w-40",
                style=_FILTER_CONTROL_STYLE,
            ),
            TextInput(
                type="date",
                name="end_date",
                value=state.end_date,
                aria_label="结束日期",
                title="结束日期",
                cls="q-input h-9 w-40",
                style=_FILTER_CONTROL_STYLE,
            ),
            ActionButton(
                "查询",
                type="submit",
                cls="q-btn h-9 min-w-[72px] whitespace-nowrap",
                style=(
                    "height:36px;width:72px;min-width:72px;flex:none;margin:0;"
                    "box-sizing:border-box;padding:0 12px;"
                ),
            ),
            method="get",
            cls="flex flex-wrap items-center gap-2",
        ),
        Div(
            _adjust_toggle(state),
            _toggle_button(state, "显示成交", "隐藏成交", "show_turnover"),
            _toggle_button(state, "显示涨跌停", "隐藏涨跌停", "show_limits"),
            _toggle_button(state, "显示ST", "隐藏ST", "show_st"),
            cls="ml-auto flex flex-wrap items-center justify-end gap-2",
        ),
        cls="mb-4 flex flex-wrap items-center gap-2",
    )


def _get_market_data(
    code: str = "",
    start_date: str = "",
    end_date: str = "",
    adjust: str = "none",
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict[str, Any]], int]:
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

            data = cast(list[dict[str, Any]], df.sort("asset").to_pandas().to_dict("records"))
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

        data = cast(list[dict[str, Any]], df.to_pandas().to_dict("records"))
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


def _market_row(
    row: Mapping[str, Any],
    asset_names: Mapping[str, str],
    state: _MarketView,
) -> Any:
    """Render one row with its display values and optional columns."""
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
    if state.show_identity:
        asset = str(row.get("asset") or "-")
        cells.extend(
            [
                Td(_display_asset(asset), cls="px-4 py-2 text-sm font-medium text-gray-900"),
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
        ]
    )
    if state.show_turnover:
        cells.extend(
            [
                Td(_market_number(row, "volume", ",.0f"), cls="px-4 py-2 text-sm text-gray-500"),
                Td(_market_number(row, "amount", ",.2f"), cls="px-4 py-2 text-sm text-gray-500"),
            ]
        )
    if state.show_limits:
        cells.extend(
            [
                Td(_market_number(row, "up_limit", ".2f"), cls="px-4 py-2 text-sm text-gray-500"),
                Td(_market_number(row, "down_limit", ".2f"), cls="px-4 py-2 text-sm text-gray-500"),
            ]
        )
    cells.append(Td(_market_number(row, "adjust", ".4f"), cls="px-4 py-2 text-sm text-gray-500"))
    if state.show_st:
        cells.append(Td(is_st, cls="px-4 py-2 text-sm text-gray-500"))
    return Tr(*cells, cls="hover:bg-gray-50")


def _build_market_table(data: list[dict[str, Any]], total: int, state: _MarketView) -> Any:
    """构建行情数据表格"""
    asset_names = _load_asset_names() if state.show_identity else {}
    headers = (["证券代码", "证券名称"] if state.show_identity else []) + [
        "日期",
        "开盘",
        "最高",
        "最低",
        "收盘",
        "涨跌",
    ]
    if state.show_turnover:
        headers.extend(["成交量", "成交额"])
    if state.show_limits:
        headers.extend(["涨停价", "跌停价"])
    headers.append("复权因子")
    if state.show_st:
        headers.append("ST")

    rows: list[Any] = []
    if data:
        rows.extend(_market_row(row, asset_names, state) for row in data)
    else:
        rows.append(
            Tr(
                Td(
                    "暂无数据",
                    colspan=str(len(headers)),
                    cls="px-4 py-8 text-center text-gray-500",
                )
            )
        )

    total_pages = max(1, (total + state.per_page - 1) // state.per_page) if total > 0 else 1
    pagination_info = (
        f"显示第 {(state.page - 1) * state.per_page + 1} 到 "
        f"{min(state.page * state.per_page, total)} 条，共 {total} 条"
        if total > 0
        else "暂无数据"
    )

    return Div(
        DatasetTable(headers, rows),
        DatasetPagination(
            pagination_info,
            state.page,
            state.per_page,
            total_pages,
            lambda number, size: state.url(page=number, per_page=size),
            pagination_button_class,
        ),
        cls="bg-white rounded-lg shadow overflow-hidden",
    )


@rt("/")
async def index(req: Request) -> Any:
    """行情数据页面"""
    state = _MarketView.from_request(req)
    logger.info(
        f"market_page called with code='{state.code}', "
        f"start_date='{state.start_date}', end_date='{state.end_date}'"
    )

    data, total = _get_market_data(
        state.code,
        state.start_date,
        state.end_date,
        state.adjust,
        state.page,
        state.per_page,
    )

    layout = MainLayout(title="行情数据")
    layout.set_sidebar_active("/system/market")

    page_content = Div(
        Div(
            Div(
                UkIcon("bar-chart-2", size=32, cls="mr-3", style=f"color: {PRIMARY_COLOR};"),
                H2("行情数据", cls="text-2xl font-bold"),
                cls="flex items-center",
            ),
            cls="mb-6",
        ),
        _filter_row(state),
        Div(_build_market_table(data, total, state), id="market-content"),
        cls="p-8",
    )

    layout.set_main_block(page_content)
    return layout.render(req)


@rt("/sync", methods="post")
async def sync_market(req: Request) -> Any:
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

        state = replace(_MarketView.from_request(req), page=1, per_page=20)
        data, total = _get_market_data(
            state.code,
            state.start_date,
            state.end_date,
            state.adjust,
            state.page,
            state.per_page,
        )
        return _build_market_table(data, total, state)
    except Exception as e:
        logger.error(f"同步行情数据失败: {e}")
        return Div(
            UkIcon("alert-circle", cls="text-red-500 mr-2"),
            f"同步失败: {str(e)}",
            cls="flex items-center p-4 bg-red-50 text-red-700 rounded-lg",
        )


def _market_number(row: Mapping[str, Any], key: str, spec: str) -> str:
    value = row.get(key)
    return format(value, spec) if value is not None else "-"
