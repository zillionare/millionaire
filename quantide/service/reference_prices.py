"""Historical close and moving-average references with explicit data semantics."""

from __future__ import annotations

import datetime
import math
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, cast

import polars as pl

if TYPE_CHECKING:
    from quantide.data.models.daily_bars import DailyBars


def positive_price(value: Any) -> float:
    """Reject missing, nonnumeric and nonfinite prices at the order boundary."""
    try:
        price = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return price if math.isfinite(price) and price > 0 else 0.0


def reference_period(price_ref: str) -> int:
    """Return the number of closed bars needed for a supported reference."""
    if price_ref == "close":
        return 1
    if not price_ref.startswith("ma"):
        return 0
    try:
        return max(0, int(price_ref[2:]))
    except ValueError:
        return 0


def historical_reference(
    store: DailyBars, asset: str, price_ref: str, *, end: datetime.date, adjust: str | None
) -> float:
    """Keep the caller's adjustment and cutoff; leave rounding to that caller."""
    period = reference_period(price_ref)
    if period == 0:
        return 0.0
    try:
        bars = cast(
            pl.DataFrame,
            store.get_bars(period, end=end, assets=[asset], eager_mode=True, adjust=adjust),
        )
        if bars.is_empty() or len(bars) < period:
            return 0.0
        closes = bars.sort("date").get_column("close").tail(period).to_list()
        prices = [positive_price(value) for value in closes]
        return sum(prices) / period if all(prices) else 0.0
    except Exception:
        return 0.0


def quote_prices(
    assets: Iterable[str], get_quote: Callable[[str], dict[str, Any] | None]
) -> dict[str, float]:
    """Return finite, positive last-traded prices from a broker's quote interface."""
    prices: dict[str, float] = {}
    for asset in assets:
        quote = get_quote(asset)
        price = positive_price((quote or {}).get("lastPrice"))
        if price:
            prices[asset] = price
    return prices
