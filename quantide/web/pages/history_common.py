"""历史持仓/委托/成交页面共用的小工具。"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any

import polars as pl

from quantide.core.enums import OrderSide, OrderStatus
from quantide.core.order_values import coerce_order_status
from quantide.web.components.asset_label import resolve_asset_name

_STATUS_LABELS = {
    OrderStatus.UNREPORTED: "未报",
    OrderStatus.WAIT_REPORTING: "待报",
    OrderStatus.REPORTED: "已报",
    OrderStatus.REPORTED_CANCEL: "已报待撤",
    OrderStatus.PARTSUCC_CANCEL: "部成待撤",
    OrderStatus.PART_CANCEL: "部成已撤",
    OrderStatus.CANCELED: "已撤",
    OrderStatus.PART_SUCC: "部成",
    OrderStatus.SUCCEEDED: "已成",
    OrderStatus.JUNK: "废单",
    OrderStatus.UNKNOWN: "未知",
}


def coerce_status(value: object) -> OrderStatus:
    return coerce_order_status(value)


def status_label(value: object) -> str:
    """返回中文委托状态。"""
    return _STATUS_LABELS.get(coerce_status(value), "未知")


def side_label(value: object) -> str:
    """返回中文买卖方向。"""
    if isinstance(value, OrderSide):
        return "买入" if value == OrderSide.BUY else ("卖出" if value == OrderSide.SELL else "未知")
    text = str(value).strip().upper()
    if text in {"BUY", "1", "买入"}:
        return "买入"
    if text in {"SELL", "-1", "卖出"}:
        return "卖出"
    return "未知"


def display_name(asset: str, fallback: str = "") -> str:
    """优先使用行内名称，否则根据代码解析。"""
    if fallback:
        return str(fallback)
    try:
        return resolve_asset_name(asset)
    except Exception:
        return asset


def history_date_range(query_params: Mapping[str, str]) -> tuple[str, str]:
    """Default history filters to the most recent thirty exchange-local days."""
    import datetime

    from quantide.core.market_time import market_today

    today = market_today()
    return (
        query_params.get("start_date") or (today - datetime.timedelta(days=30)).isoformat(),
        query_params.get("end_date") or today.isoformat(),
    )


def history_rows(
    query: Callable[..., pl.DataFrame],
    account_id: str,
    start_date: str,
    end_date: str,
) -> Iterator[dict[str, Any]]:
    """Query one account history using a consistently parsed date range."""
    import datetime

    frame = query(
        portfolio_id=account_id,
        start=datetime.date.fromisoformat(start_date),
        end=datetime.date.fromisoformat(end_date),
    )
    return frame.iter_rows(named=True)


def history_trade_identity(row: Mapping[str, Any]) -> dict[str, object]:
    """Resolve shared order/trade display fields once."""
    asset = str(row.get("asset", "") or "")
    return {
        "tm": str(row.get("tm", ""))[:19],
        "asset": asset,
        "name": display_name(asset, row.get("name", "")),
        "side": side_label(row.get("side")),
        "price": row.get("price") or 0,
        "shares": row.get("shares") or 0,
    }
