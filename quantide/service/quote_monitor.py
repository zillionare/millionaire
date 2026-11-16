"""实时行情监视器（运维页面用）。

与 ``MarketDataHub`` 不同，本模块**不做订阅过滤**，记录总线上收到的全部快照，
用于人工确认行情源是否正常、最新批次覆盖多少标的、延迟多大。
"""

from __future__ import annotations

import datetime
import threading
from typing import Any

from quantide.core.enums import Topics
from quantide.core.market_time import market_now
from quantide.core.market_values import float_or_none as _to_float
from quantide.core.message import msg_hub


class QuoteMonitor:
    """缓存最近一轮行情快照与推送统计。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started = False
        self._quotes: dict[str, dict[str, Any]] = {}
        self._last_received_at: datetime.datetime | None = None
        self._last_batch_at: datetime.datetime | None = None
        self._last_batch_size = 0
        self._messages = 0
        self._updates = 0

    def start(self) -> None:
        """订阅行情总线（幂等）。"""
        with self._lock:
            if self._started:
                return
            msg_hub.subscribe(Topics.QUOTES_ALL.value, self._on_quotes)
            self._started = True

    def stop(self) -> None:
        """Release the subscription when the owning application shuts down."""
        with self._lock:
            if self._started:
                msg_hub.unsubscribe(Topics.QUOTES_ALL.value, self._on_quotes)
                self._started = False

    def _on_quotes(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or not payload:
            return
        now = market_now()
        updated = 0
        with self._lock:
            for symbol, raw in payload.items():
                if not isinstance(raw, dict):
                    continue
                price = _to_float(raw.get("lastPrice"))
                if price is None:
                    price = _to_float(raw.get("price"))
                if price is None or price <= 0:
                    continue
                quote_ts = raw.get("ts")
                if not isinstance(quote_ts, datetime.datetime):
                    quote_ts = None
                self._quotes[str(symbol)] = {
                    "symbol": str(symbol),
                    "name": raw.get("name"),
                    "price": price,
                    "prev_close": _to_float(raw.get("prev_close")),
                    "open": _to_float(raw.get("open")),
                    "high": _to_float(raw.get("high")),
                    "low": _to_float(raw.get("low")),
                    "volume": _to_float(raw.get("volume")),
                    "amount": _to_float(raw.get("amount")),
                    "up_limit": _to_float(raw.get("up_limit")),
                    "down_limit": _to_float(raw.get("down_limit")),
                    "quote_ts": quote_ts,
                    "received_at": now,
                }
                updated += 1
            self._messages += 1
            self._updates += updated
            if updated:
                self._last_received_at = now
            self._last_batch_at = now
            self._last_batch_size = updated

    def status(self) -> dict[str, Any]:
        """返回推送统计。"""
        with self._lock:
            return {
                "started": self._started,
                "symbols": len(self._quotes),
                "messages": self._messages,
                "updates": self._updates,
                "last_received_at": self._last_received_at,
                "last_batch_at": self._last_batch_at,
                "last_batch_size": self._last_batch_size,
            }

    def snapshot(
        self,
        query: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """返回最新快照（按成交额降序，可过滤代码/名称）。"""
        with self._lock:
            rows = list(self._quotes.values())
        return select_snapshot_rows(rows, query, limit)


def select_snapshot_rows(
    rows: list[dict[str, Any]], query: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Filter and rank snapshot rows shared by live and persisted views."""
    text = str(query or "").strip().upper()
    if text:
        rows = [
            row
            for row in rows
            if text in row["symbol"].upper() or text in str(row.get("name") or "").upper()
        ]
    rows.sort(
        key=lambda row: (row.get("amount") or 0.0, row.get("volume") or 0.0),
        reverse=True,
    )
    return rows[: max(1, int(limit))]


#: 全局单例
quote_monitor = QuoteMonitor()

__all__ = ["QuoteMonitor", "quote_monitor", "select_snapshot_rows"]
