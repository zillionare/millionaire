"""Reference prices and account statistics for the trading page."""

import datetime
from typing import Any

import polars as pl
from fasthtml.common import *
from monsterui.all import *

from quantide.data.fetchers.registry import get_data_fetcher
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.service.market_data_hub import market_data_hub


def _format_trade_metric(value: float | None) -> str:
    """Format a trade metric for compact UI display.

    Args:
        value: The numeric value to format.

    Returns:
        A two-decimal string, or an empty string when unavailable.
    """
    if value is None:
        return ""
    return f"{value:.2f}"


def _extract_recent_trade_dates(
    calendar_frame: Any, end: datetime.date, periods: int
) -> list[datetime.date]:
    """Extract recent open trade dates from a fetcher calendar response.

    Args:
        calendar_frame: Calendar data returned by the data fetcher.
        end: Preferred end date for the lookup window.
        periods: Number of dates to keep.

    Returns:
        A sorted list of recent trade dates.
    """
    if calendar_frame is None or calendar_frame.empty:
        return []

    dates: list[datetime.date] = []
    for index, row in calendar_frame.iterrows():
        if not bool(row.get("is_open", 1)):
            continue
        raw_date = row.get("date", index)
        if hasattr(raw_date, "date"):
            raw_date = raw_date.date()
        dates.append(raw_date)

    if not dates:
        return []

    dates = sorted(set(dates))
    eligible_dates = [trade_date for trade_date in dates if trade_date <= end]
    return (eligible_dates or dates)[-periods:]


def _resolve_trade_reference_dates(
    fetcher: Any, end: datetime.date, periods: int
) -> list[datetime.date]:
    """Resolve fallback trade dates for the trade panel.

    Args:
        fetcher: Active market data fetcher.
        end: Preferred end date.
        periods: Number of trade dates to retrieve.

    Returns:
        A list of trade dates for fetcher fallback queries.
    """
    start = end - datetime.timedelta(days=periods * 3)
    try:
        trade_dates = calendar.get_trade_dates(start, end)[-periods:]
    except Exception:
        trade_dates = []
    if trade_dates:
        return trade_dates

    lookback_start = end - datetime.timedelta(days=max(periods * 30, 365 * 3))
    try:
        calendar_frame = fetcher.fetch_calendar(lookback_start)
    except Exception:
        return [end]

    resolved_dates = _extract_recent_trade_dates(calendar_frame, end, periods)
    return resolved_dates or [end]


def _build_asset_stats(asset: str) -> dict[str, str | bool]:
    """Build reference price stats for the selected asset.

    Args:
        asset: The selected stock code.

    Returns:
        A payload suitable for the trade reference panel.
    """
    payload: dict[str, str | bool] = {
        "visible": False,
        "close": "",
        "ma5": "",
        "ma10": "",
        "ma20": "",
        "ma30": "",
        "ma60": "",
        "current": "",
    }
    bars = _load_trade_reference_bars(asset, datetime.date.today(), 60)
    if bars.is_empty():
        return payload

    ordered = bars.sort("date")
    closes = [float(value) for value in ordered.get_column("close").to_list()]
    if not closes:
        return payload

    current_price = _resolve_live_current_price(asset)
    payload["visible"] = True
    payload["close"] = _format_trade_metric(closes[-1])
    # A historical close is a reference metric, not a current quote.  Keep
    # the current-price field empty until MarketDataHub has a real snapshot.
    payload["current"] = _format_trade_metric(current_price) if current_price > 0 else ""
    for period in (5, 10, 20, 30, 60):
        if len(closes) >= period:
            payload[f"ma{period}"] = _format_trade_metric(sum(closes[-period:]) / period)
    return payload


def _load_trade_reference_bars(asset: str, end: datetime.date, periods: int) -> pl.DataFrame:
    """Load recent bars for the trade panel from local storage or fetcher fallback.

    Args:
        asset: Stock code.
        end: End date.
        periods: Number of trade dates to retrieve.

    Returns:
        A date-sorted Polars DataFrame.
    """
    try:
        bars = daily_bars.get_bars(periods, end=end, assets=[asset], eager_mode=True, adjust="qfq")
    except Exception:
        bars = pl.DataFrame()
    if not bars.is_empty():
        return bars.sort("date")

    try:
        fetcher = get_data_fetcher()
        trade_dates = _resolve_trade_reference_dates(fetcher, end, periods)
        fallback_frame, _ = fetcher.fetch_bars_ext(trade_dates)
    except Exception:
        return pl.DataFrame()
    if fallback_frame is None or fallback_frame.empty:
        return pl.DataFrame()

    fallback = pl.from_pandas(fallback_frame).filter(pl.col("asset") == asset)
    if fallback.is_empty():
        return fallback
    return fallback.with_columns(pl.col("date").cast(pl.Date)).sort("date")


def _resolve_local_trade_close(asset: str) -> float:
    """本地日线的最新收盘价（不触发网络拉取）。"""
    if not asset:
        return 0.0
    try:
        bars = daily_bars.get_bars(
            5,
            end=datetime.date.today(),
            assets=[asset],
            eager_mode=True,
            adjust="qfq",
        )
    except Exception:
        return 0.0
    if bars is None or bars.is_empty():
        return 0.0
    try:
        value = float(bars.sort("date").row(-1, named=True).get("close") or 0)
    except Exception:
        return 0.0
    return value if value > 0 else 0.0


def _resolve_trade_reference_close(asset: str) -> float:
    """Resolve the latest reference close price for a trade symbol.

    Args:
        asset: Stock code.

    Returns:
        Latest close price when available, otherwise ``0.0``.
    """
    if not asset:
        return 0.0
    bars = _load_trade_reference_bars(asset, datetime.date.today(), 5)
    if bars.is_empty():
        return 0.0
    try:
        close_value = float(bars.sort("date").row(-1, named=True).get("close") or 0)
    except Exception:
        return 0.0
    return close_value if close_value > 0 else 0.0


def _resolve_live_current_price(asset: str) -> float:
    """Resolve the latest current price for the trade panel.

    Args:
        asset: Stock code.

    Returns:
        Current quote price when available, otherwise ``0.0``.
    """
    if not asset:
        return 0.0
    _maybe_start_live_quote()
    try:
        snapshot = market_data_hub.snapshot([asset]).get(asset)
        if snapshot is not None:
            price = float(getattr(snapshot, "price", 0) or 0)
            if price > 0:
                return price
    except Exception:
        pass
    quote = market_data_hub.get_quote(asset)
    if not quote:
        return 0.0
    for key in ("price", "lastPrice"):
        try:
            value = float(quote.get(key) or 0)
        except Exception:
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _maybe_start_live_quote() -> None:
    """Compatibility hook: start the sole MarketDataHub subscription."""
    if not market_data_hub.is_running:
        market_data_hub.start()


def _build_live_quote_payload(asset: str) -> dict[str, str | bool]:
    """Build a lightweight live quote payload for UI polling.

    Args:
        asset: Stock code.

    Returns:
        Quote payload for the trade page.
    """
    current_price = _resolve_live_current_price(asset)
    return {
        "asset": asset,
        "current": _format_trade_metric(current_price) if current_price > 0 else "",
        "visible": current_price > 0,
    }
