"""Shared factor page labels and number formatting."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Span

from quantide.core.market_values import datetime_or_none

LOOKBACK_LABELS = {"1y": "1 年", "3y": "3 年", "5y": "5 年", "all": "全部"}
PRICE_LABELS = {"open": "开盘价", "close": "收盘价"}
STATUS_LABELS = {
    "normal": "正常",
    "uninitialized": "未建立",
    "calculating": "计算中",
    "stale_data": "行情已更新，待跟踪",
    "source_unavailable": "来源版本不可用，待跟踪",
    "failed": "计算失败",
    "insufficient": "数据不足",
    "interrupted": "已中断",
    "disabled": "已关闭",
}


def status_badge(status: str) -> Span:
    tone = {
        "normal": "bg-green-50 text-green-700",
        "failed": "bg-red-50 text-red-700",
        "calculating": "bg-gray-100 text-gray-700",
        "stale_data": "bg-amber-50 text-amber-700",
        "source_unavailable": "bg-amber-50 text-amber-700",
        "insufficient": "bg-amber-50 text-amber-700",
        "disabled": "bg-gray-100 text-gray-600",
    }.get(status, "bg-gray-100 text-gray-600")
    return Span(STATUS_LABELS.get(status, status), cls=f"rounded-full px-2 py-1 text-xs {tone}")


def fmt_number(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):+.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def fmt_percent(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:+.2f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_time(value: Any) -> str:
    parsed = datetime_or_none(value)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else "—"
