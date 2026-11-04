"""Official Tushare snapshots normalized into the existing quote contract."""

import datetime
import math
import threading
from collections.abc import Iterable
from typing import Any, cast

import pandas as pd
import tushare as ts

from quantide.config.settings import get_tushare_token
from quantide.core.market_time import market_now


def _timestamp(value: Any, now: datetime.datetime) -> datetime.datetime | None:
    text = str(value or "").strip()
    if len(text) == 8 and text.count(":") == 2:
        return None
    try:
        parsed = pd.to_datetime(text, format="%Y%m%d%H%M%S" if text.isdigit() else None)
        if pd.isna(parsed):
            return None
        stamp = parsed.to_pydatetime()
        return stamp.replace(tzinfo=now.tzinfo) if stamp.tzinfo is None else stamp
    except (TypeError, ValueError, OverflowError):
        return None


def normalized_snapshot(
    row: dict[str, Any], limits: dict[str, Any], now: datetime.datetime
) -> dict[str, float | datetime.datetime] | None:
    """Reject stale or incomplete records rather than publish invented prices or limits."""
    stamp = _timestamp(row.get("trade_time"), now)
    if stamp is None or stamp.date() != now.date():
        return None
    if not -5 <= (now - stamp).total_seconds() <= 150:
        return None
    try:
        values = {name: float(row[name]) for name in ("open", "high", "low", "close", "pre_close")}
        up, down = float(limits["up_limit"]), float(limits["down_limit"])
        if not all(math.isfinite(value) and value > 0 for value in (*values.values(), up, down)):
            return None
        if up < down:
            return None
        volume, amount = float(row["vol"]) / 100, float(row["amount"]) / 1000
        if not all(math.isfinite(value) and value >= 0 for value in (volume, amount)):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "price": values["close"],
        "prev_close": values["pre_close"],
        "open": values["open"],
        "high": values["high"],
        "low": values["low"],
        "volume": volume,
        "amount": amount,
        "ts": stamp,
        "up_limit": up,
        "down_limit": down,
    }


def compatible_snapshot(row: dict[str, Any]) -> bool:
    """Confirm useful prices and a dated timestamp before offering automatic setup."""
    try:
        values = [float(row[name]) for name in ("open", "high", "low", "close", "pre_close")]
        return all(math.isfinite(value) and value > 0 for value in values) and (
            _timestamp(row.get("trade_time"), market_now()) is not None
        )
    except (KeyError, TypeError, ValueError):
        return False


class TushareRealtimeFetcher:
    """Fetch subscribed A-share snapshots and exact same-day price limits."""

    def __init__(self, client: Any = None, cancel: threading.Event | None = None) -> None:
        self.client = client or ts.pro_api(token=get_tushare_token(), timeout=5)
        self._day: datetime.date | None = None
        self._limits: dict[str, dict[str, Any]] = {}
        self._cancel = cancel or threading.Event()

    def fetch_quote_snapshot(
        self, symbols: Iterable[str], now: datetime.datetime | None = None
    ) -> dict[str, dict[str, float | datetime.datetime]]:
        now = now or market_now()
        if not self._load_limits(now):
            return {}
        result: dict[str, dict[str, float | datetime.datetime]] = {}
        symbols = list(dict.fromkeys(symbols))
        for index in range(0, len(symbols), 500):
            if self._cancel.is_set():
                break
            frame = self.client.rt_k(
                ts_code=",".join(symbols[index : index + 500]),
                fields="ts_code,open,high,low,close,pre_close,vol,amount,trade_time",
            )
            result.update(self._normalized_rows(frame, now))
        return {asset: row for asset, row in result.items() if asset in symbols}

    def _load_limits(self, now: datetime.datetime) -> bool:
        if self._day == now.date():
            return True
        self._limits = {}
        self._day = None
        day = now.strftime("%Y%m%d")
        frame = self.client.stk_limit(trade_date=day)
        if frame is None or frame.empty or "trade_date" not in frame.columns:
            return False
        self._limits = {
            row["ts_code"]: row for row in frame.to_dict("records") if str(row["trade_date"]) == day
        }
        if not self._limits:
            return False
        self._day = now.date()
        return True

    def _normalized_rows(
        self, frame: pd.DataFrame | None, now: datetime.datetime
    ) -> dict[str, dict[str, float | datetime.datetime]]:
        if frame is None:
            return {}
        result: dict[str, dict[str, float | datetime.datetime]] = {}
        for row in frame.to_dict("records"):
            quote = normalized_snapshot(
                cast(dict[str, Any], row), self._limits.get(row["ts_code"], {}), now
            )
            if quote is not None:
                result[row["ts_code"]] = quote
        return result
