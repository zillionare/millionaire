"""Convert gateway history payloads into the shared view models."""

import datetime
from typing import Any

from fasthtml.common import *
from monsterui.all import *

from quantide.core.enums import BidType
from quantide.core.runtime.gateway_broker import (
    _coerce_order_side,
    _coerce_order_status,
)
from quantide.data.models import Order, Position


def _coerce_gateway_position(
    payload: dict[str, Any],
    portfolio_id: str = "gateway",
) -> Position:
    """把 gateway 返回的持仓 dict 包装成 ``Position`` 数据类."""
    today = datetime.date.today()
    asset = str(payload.get("symbol") or "")
    shares = float(payload.get("shares") or 0)
    avail = float(payload.get("avail") or 0)
    price = float(payload.get("price") or payload.get("cost") or 0)
    mv = float(payload.get("market_value") or 0)
    profit = float(payload.get("float_profit") or 0)
    return Position(
        portfolio_id=portfolio_id,
        dt=today,
        asset=asset,
        shares=shares,
        avail=avail,
        price=price,
        profit=profit,
        mv=mv,
    )


def _coerce_gateway_order(
    payload: dict[str, Any],
    portfolio_id: str = "gateway",
) -> Order:
    """把 gateway 返回的委托 dict 包装成 ``Order`` 数据类."""
    asset = str(payload.get("symbol") or "")
    side = _coerce_order_side(str(payload.get("side") or ""))
    status = _coerce_order_status(str(payload.get("status") or ""))
    shares = float(payload.get("shares") or 0)
    price = float(payload.get("price") or 0)
    filled = float(payload.get("filled") or 0)
    time_text = str(payload.get("time") or "")
    qtoid = str(payload.get("qtoid") or payload.get("order_id") or payload.get("foid") or "")
    if not qtoid:
        from uuid import uuid4

        qtoid = f"gw-{uuid4()}"
    tm = _parse_order_time_text(time_text)
    return Order(
        portfolio_id=portfolio_id,
        asset=asset,
        side=side,
        shares=shares,
        bid_type=BidType.FIXED,
        tm=tm,
        price=price,
        filled=filled,
        foid=qtoid,
        status=status,
    )


def _parse_order_time_text(time_text: str) -> datetime.datetime:
    """把 ``"HH:MM:SS"`` / ``"YYYY-MM-DD HH:MM:SS"`` / ISO 字符串解析成 datetime.

    gateway 委托响应里的 ``time`` 字段是字符串，三种格式都可能。
    解析失败时回退到 ``datetime.datetime.now()``，不让单条坏数据把整页炸掉。
    """
    text = (time_text or "").strip()
    if not text:
        return datetime.datetime.now()
    # ISO 格式（带 T 或带 -）
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%H:%M:%S",
    ):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.datetime.now()
