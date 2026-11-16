"""系统维护 - 实时行情监控页面。"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from fasthtml.common import (
    H2,
    Button,
    Div,
    Form,
    Input,
    P,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)
from starlette.requests import Request

from quantide.config.paths import get_app_config_dir
from quantide.config.settings import get_timezone
from quantide.core.market_values import datetime_or_none, float_or_none
from quantide.data.models.calendar import calendar
from quantide.data.models.stocks import stock_list
from quantide.service.quote_monitor import quote_monitor, select_snapshot_rows
from quantide.web.application import fast_app
from quantide.web.components.navigation import SystemBreadcrumb
from quantide.web.layouts.main import MainLayout
from quantide.web.session_data import SessionData
from quantide.web.theme import AppTheme

system_realtime_app, rt = fast_app(hdrs=AppTheme.headers())

_POLL = "every 3s [document.visibilityState === 'visible']"


def _breadcrumb() -> Div:
    return SystemBreadcrumb("实时行情")


def _is_session(now: datetime.datetime) -> bool:
    if not calendar.is_trade_day(now):
        return False
    tm = now.time()
    return datetime.time(9, 30) <= tm <= datetime.time(11, 30) or (
        datetime.time(13, 0) <= tm <= datetime.time(15, 0)
    )


def _status_card(label: str, value: str, hint: str = "", tone: str = "gray") -> Div:
    tone_cls = {
        "green": "text-green-600",
        "amber": "text-gray-600",
        "red": "text-red-600",
        "blue": "text-[#e41815]",
        "gray": "text-gray-900",
    }.get(tone, "text-gray-900")
    return Div(
        P(label, cls="text-xs text-gray-500"),
        P(value, cls=f"mt-1 text-lg font-semibold tabular-nums {tone_cls}"),
        P(hint, cls="mt-1 text-[11px] text-gray-400"),
        cls="bg-white px-4 py-3",
    )


def _freshness(now: datetime.datetime, last: datetime.datetime | None) -> tuple[str, str, str]:
    """返回 (文案, 颜色, 提示)。"""
    if not _is_session(now):
        return "休市", "gray", "非交易时段"
    if last is None:
        return "中断", "red", "尚未收到任何行情"
    age = max(0.0, (now - last).total_seconds())
    if age <= 15:
        return "实时", "green", f"延迟 {age:.0f}s"
    if age <= 60:
        return "延迟", "amber", f"延迟 {age:.0f}s"
    return "中断", "red", f"已 {age:.0f}s 无更新"


def _change_cls(change_pct: float | None) -> str:
    if change_pct is None or change_pct == 0:
        return "text-gray-700"
    return "text-red-500" if change_pct > 0 else "text-green-600"


def _quote_row(row: Any, as_of: datetime.datetime) -> Any:
    """Render one row using a frozen reference time for close snapshots."""
    prev_close = row.get("prev_close")
    change_pct = None
    if prev_close and prev_close > 0:
        change_pct = (row["price"] - prev_close) / prev_close * 100
    received_at = row.get("received_at")
    delay = (
        max(0.0, (as_of - received_at).total_seconds())
        if isinstance(received_at, datetime.datetime)
        else None
    )
    quote_ts = row.get("quote_ts")
    return Tr(
        Td(row["symbol"], cls="px-3 py-2 font-mono text-xs text-gray-700"),
        Td(row.get("name") or "-", cls="px-3 py-2 text-gray-700"),
        Td(f"{row['price']:,.2f}", cls="px-3 py-2 text-right tabular-nums"),
        Td(
            f"{change_pct:+.2f}%" if change_pct is not None else "-",
            cls=f"px-3 py-2 text-right tabular-nums {_change_cls(change_pct)}",
        ),
        Td(
            f"{prev_close:,.2f}" if prev_close else "-",
            cls="px-3 py-2 text-right tabular-nums text-gray-500",
        ),
        Td(
            f"{row.get('volume'):,.0f}" if row.get("volume") is not None else "-",
            cls="px-3 py-2 text-right tabular-nums text-gray-600",
        ),
        Td(
            f"{row.get('amount'):,.0f}" if row.get("amount") is not None else "-",
            cls="px-3 py-2 text-right tabular-nums text-gray-600",
        ),
        Td(
            quote_ts.strftime("%H:%M:%S") if isinstance(quote_ts, datetime.datetime) else "-",
            cls="px-3 py-2 text-right tabular-nums text-gray-500",
        ),
        Td(
            f"{delay:.1f}s" if delay is not None else "-",
            cls="px-3 py-2 text-right tabular-nums text-gray-500",
        ),
        cls="border-b border-gray-50 last:border-0",
    )


def _local_naive(value: datetime.datetime | None) -> datetime.datetime | None:
    """Normalize persisted timestamps to exchange-local naive time."""
    if value is None:
        return None
    return value.astimezone(get_timezone()).replace(tzinfo=None) if value.tzinfo else value


def _snapshot_quote(raw: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(raw.get("symbol") or "").strip()
    price = float_or_none(raw.get("price"))
    if not symbol or price is None or price <= 0:
        return None
    return {
        "symbol": symbol,
        "name": raw.get("name"),
        "price": price,
        "prev_close": float_or_none(raw.get("prev_close")),
        "open": float_or_none(raw.get("open")),
        "high": float_or_none(raw.get("high")),
        "low": float_or_none(raw.get("low")),
        "volume": float_or_none(raw.get("volume")),
        "amount": float_or_none(raw.get("amount")),
        "up_limit": float_or_none(raw.get("up_limit")),
        "down_limit": float_or_none(raw.get("down_limit")),
        "quote_ts": _local_naive(datetime_or_none(raw.get("quote_ts"))),
        "received_at": _local_naive(datetime_or_none(raw.get("received_at"))),
    }


def _read_snapshot_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _snapshot_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    quotes = payload.get("quotes")
    if not isinstance(quotes, list):
        return []
    return [
        quote
        for raw in quotes
        if isinstance(raw, dict)
        for quote in [_snapshot_quote(raw)]
        if quote is not None
    ]


def _latest_snapshot_rows(
    query: str,
) -> tuple[list[dict[str, Any]], datetime.datetime | None]:
    directory = get_app_config_dir() / "market-snapshots"
    for path in sorted(directory.glob("*.json"), reverse=True):
        payload = _read_snapshot_payload(path)
        if payload is None:
            continue
        rows = _snapshot_rows_from_payload(payload)
        if rows:
            captured_at = _local_naive(datetime_or_none(payload.get("captured_at")))
            return select_snapshot_rows(rows, query), captured_at
    return [], None


def _rows_for_content(
    now: datetime.datetime, query: str
) -> tuple[list[dict[str, Any]], datetime.datetime | None]:
    if _is_session(now):
        return quote_monitor.snapshot(query=query, limit=50), None
    rows, captured_at = _latest_snapshot_rows(query)
    if rows:
        return rows, captured_at
    return quote_monitor.snapshot(query=query, limit=50), None


def _render_rows(
    now: datetime.datetime, rows: list[dict[str, Any]], as_of: datetime.datetime
) -> list[Any]:
    if not rows:
        if _is_session(now):
            title = "尚未收到行情"
            hint = "行情数据尚未到达，请稍后刷新。"
        else:
            title = "暂无最近行情数据"
            hint = "休市期间不拉取新的实时行情。"
        return [
            Tr(
                Td(
                    Div(
                        P(title, cls="text-sm font-medium text-gray-500"),
                        P(hint, cls="mt-1 text-xs text-gray-400"),
                        cls="py-12 text-center",
                    ),
                    colspan=9,
                )
            )
        ]
    return [_quote_row(row, as_of) for row in rows]


def _data_health(now: datetime.datetime) -> list[Any]:
    items: list[Any] = []
    try:
        from quantide.data import get_limit_price_store

        limits = get_limit_price_store().limits_map(now.date())
        expected = int(stock_list.size or 0)
        count = len(limits)
        coverage = count / expected if expected else (1.0 if count else 0.0)
        tone = (
            "bg-green-50 text-green-700"
            if coverage >= 0.9
            else ("bg-gray-100 text-gray-700" if coverage >= 0.5 else "bg-red-50 text-red-600")
        )
        label = "涨跌停价已获取" if count else "涨跌停价未获取"
        items.append(
            Span(
                f"{label}：{count}/{expected or '?'}（{coverage * 100:.0f}%）",
                cls=f"rounded-full px-2.5 py-1 text-xs {tone}",
            )
        )
    except Exception:
        items.append(
            Span("涨跌停价未获取", cls="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-500")
        )
    return items


def _render_content(now: datetime.datetime, query: str) -> Div:
    session = _is_session(now)
    status = quote_monitor.status()
    rows, snapshot_captured_at = _rows_for_content(now, query)
    if session:
        last_received = status.get("last_received_at")
        last_hint = "行情总线最近一次推送"
        as_of = now
    else:
        last_received = snapshot_captured_at or status.get("last_received_at")
        last_hint = "休市快照缓存时间"
        as_of = snapshot_captured_at or last_received or now
    freshness, tone, hint = _freshness(now, last_received)
    last_text = (
        last_received.strftime("%H:%M:%S") if isinstance(last_received, datetime.datetime) else "—"
    )
    last_batch = (
        status["last_batch_at"].strftime("%H:%M:%S")
        if isinstance(status.get("last_batch_at"), datetime.datetime)
        else "—"
    )
    panel_url = "/system/realtime/panel"
    return Div(
        H2("实时行情", cls="text-lg font-semibold text-gray-900"),
        Div(
            _status_card("行情状态", freshness, hint, tone),
            _status_card("最后更新", last_text, last_hint),
            _status_card(
                "覆盖标的",
                f"{(status['symbols'] if session else len(rows)):,}",
                "当前缓存的最新快照数" if session else "休市快照缓存标的数",
            ),
            _status_card(
                "累计推送", f"{status['messages']:,}", f"最新批次 {status['last_batch_size']:,} 只"
            ),
            _status_card("最新批次", last_batch, "接收时间"),
            _status_card(
                "行情源",
                "运行中" if status["started"] else "未启动",
                "监视器订阅状态",
                "green" if status["started"] else "red",
            ),
            cls=(
                "mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border "
                "border-gray-100 bg-gray-100 md:grid-cols-3 xl:grid-cols-6"
            ),
        ),
        Div(
            Form(
                Input(
                    name="q",
                    value=query,
                    autocomplete="off",
                    placeholder="输入代码或名称过滤，例如 600519 / 茅台",
                    style="height:2rem;min-height:2rem;box-sizing:border-box;padding-top:0;padding-bottom:0;",
                    cls=(
                        "h-8 w-full max-w-xs rounded-lg border border-gray-200 bg-white "
                        "px-3 text-sm leading-8 outline-none focus:border-[#e41815] "
                        "focus:ring-2 focus:ring-[#e41815]/10"
                    ),
                ),
                Button(
                    "筛选",
                    type="submit",
                    style="height:2rem;min-height:2rem;width:64px;flex:none;box-sizing:border-box;",
                    cls=(
                        "inline-flex h-8 w-16 flex-none items-center justify-center "
                        "whitespace-nowrap rounded-lg border border-gray-200 "
                        "bg-white px-0 text-sm font-medium text-gray-600 transition "
                        "hover:bg-gray-50 hover:text-gray-900"
                    ),
                ),
                hx_get="/system/realtime/panel",
                hx_target="#realtime-panel",
                hx_swap="outerHTML",
                id="realtime-filter",
                cls="flex items-center gap-2",
            ),
            Div(*_data_health(now), cls="flex flex-wrap items-center gap-2"),
            cls="mt-4 flex flex-wrap items-center justify-between gap-3",
        ),
        Div(
            Div(
                Table(
                    Thead(
                        Tr(
                            Th("代码", cls="px-3 py-2 text-left text-xs font-medium text-gray-500"),
                            Th("名称", cls="px-3 py-2 text-left text-xs font-medium text-gray-500"),
                            Th(
                                "最新价",
                                cls="px-3 py-2 text-right text-xs font-medium text-gray-500",
                            ),
                            Th(
                                "涨跌幅",
                                cls="px-3 py-2 text-right text-xs font-medium text-gray-500",
                            ),
                            Th(
                                "昨收", cls="px-3 py-2 text-right text-xs font-medium text-gray-500"
                            ),
                            Th(
                                "成交量(手)",
                                cls="px-3 py-2 text-right text-xs font-medium text-gray-500",
                            ),
                            Th(
                                "成交额(千元)",
                                cls="px-3 py-2 text-right text-xs font-medium text-gray-500",
                            ),
                            Th(
                                "行情时间",
                                cls="px-3 py-2 text-right text-xs font-medium text-gray-500",
                            ),
                            Th(
                                "接收延迟",
                                cls="px-3 py-2 text-right text-xs font-medium text-gray-500",
                            ),
                            cls="border-b border-gray-100",
                        )
                    ),
                    Tbody(*_render_rows(now, rows, as_of)),
                    cls="w-full text-sm",
                ),
                cls="overflow-x-auto",
            ),
            P(
                "默认按成交额降序展示前 50 只；完整行情以发布者推送为准。",
                cls="mt-3 text-[11px] text-gray-400",
            ),
            cls="mt-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
        ),
        **(
            {
                "hx_get": panel_url,
                "hx_include": "#realtime-filter",
                "hx_trigger": _POLL,
                "hx_swap": "outerHTML",
            }
            if session
            else {}
        ),
        id="realtime-panel",
    )


@rt("/")
def index(req: Request, session: SessionData) -> Any:
    layout = MainLayout(title="实时行情", user=session.get("auth"))
    layout.set_sidebar_active("/system/realtime")
    layout.set_main_block(
        lambda: Div(
            _breadcrumb(),
            Div(
                _render_content(
                    datetime.datetime.now(),
                    req.query_params.get("q", ""),
                ),
                cls="max-w-[1400px] mx-auto w-full",
            ),
            cls="space-y-6 max-w-[1400px] mx-auto w-full",
        )
    )
    return layout.render(req)


@rt("/panel")
def panel(req: Request) -> Any:
    return _render_content(
        datetime.datetime.now(),
        req.query_params.get("q", ""),
    )
