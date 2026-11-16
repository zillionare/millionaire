"""Rebuild weighted position costs from committed trades, including purchase fees."""

from collections.abc import Iterable
from typing import Any

from quantide.core.enums import OrderSide
from quantide.core.order_values import coerce_order_side


def _apply_cost(previous: tuple[float, float], row: dict[str, Any]) -> tuple[float, float]:
    shares, average = previous
    quantity = float(row.get("shares") or 0)
    if quantity <= 0:
        return previous
    side = coerce_order_side(row.get("side"))
    if side == OrderSide.BUY:
        total = shares * average + float(row.get("amount") or 0) + float(row.get("fee") or 0)
        shares += quantity
        average = total / shares if shares > 0 else 0.0
    elif side == OrderSide.SELL:
        shares -= quantity
        if shares <= 0:
            shares, average = 0.0, 0.0
    return shares, average


def position_costs(rows: Iterable[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """Calculate only from facts; callers decide whether history agrees with their snapshot."""
    state: dict[str, tuple[float, float]] = {}
    for row in rows:
        asset = str(row.get("asset") or "")
        if asset:
            state[asset] = _apply_cost(state.get(asset, (0.0, 0.0)), row)
    return state
