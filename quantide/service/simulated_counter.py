"""Independent, persistent demonstration counter. It never connects to a broker.

The simulator consumes orders and quotes and derives fills itself. It neither
imports PaperBroker nor accepts precomputed fills or expected account results.
"""

import copy
import datetime
import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quantide.config.output_paths import external_runtime_path


class SimulatedCounter:
    """A small long-only A-share counter with T+1 and idempotent client IDs."""

    def __init__(
        self,
        path: str | Path,
        principal: float = 10000.0,
        commission: float = 0.0,
        stamp_tax: float = 0.0,
    ) -> None:
        if str(path) != ":memory:":
            path = external_runtime_path(path)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT)"
        )
        row = self._connection.execute("SELECT data FROM state WHERE id=1").fetchone()
        self.state: dict[str, Any] = (
            json.loads(row[0])
            if row
            else {
                "cash": principal,
                "principal": principal,
                "commission": commission,
                "stamp_tax": stamp_tax,
                "positions": {},
                "orders": {},
                "trades": [],
                "quotes": {},
                "day": "",
                "sequence": 0,
            }
        )
        self._save()

    def close(self) -> None:
        """Release the counter's own database, independently of the application DB."""
        self._connection.close()

    def _save(self) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO state VALUES (1, ?)",
                (json.dumps(self.state, allow_nan=False),),
            )

    def _mutate[T](self, operation: Callable[[], T]) -> T:
        with self._lock:
            before = copy.deepcopy(self.state)
            try:
                result = operation()
                self._save()
                return result
            except BaseException:
                self.state = before
                raise

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        """Accept once per client ID; a repeated request returns the original order."""

        def accept() -> dict[str, Any]:
            identity = str(request["client_order_id"])
            if not identity:
                raise ValueError("client_order_id is required")
            previous = self.state["orders"].get(identity)
            if previous is not None:
                if previous["request"] != request:
                    raise ValueError("client_order_id reused with different order content")
                return copy.deepcopy(previous)
            self._validate_order(request)
            order = {"request": dict(request), "order_id": identity, "filled": 0, "status": "open"}
            self.state["orders"][identity] = order
            self._match(order)
            return copy.deepcopy(order)

        return self._mutate(accept)

    def _validate_order(self, request: dict[str, Any]) -> None:
        shares = float(request["shares"])
        if shares <= 0 or request["side"] not in {"buy", "sell"}:
            raise ValueError("Invalid quantity or side")
        if request["side"] == "buy" and shares % 100:
            raise ValueError("Buy quantity must be a multiple of 100")
        if request["side"] == "sell":
            position = self.state["positions"].get(request["asset"], {})
            if shares > position.get("avail", 0):
                raise ValueError("Insufficient available position (T+1)")

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Advance replay time and match outstanding orders against actual quotes."""

        def update() -> dict[str, Any]:
            day = datetime.datetime.fromisoformat(payload["time"]).date().isoformat()
            if self.state["day"] and day < self.state["day"]:
                raise ValueError("Simulation clock cannot move backwards")
            if day != self.state["day"]:
                for position in self.state["positions"].values():
                    position["avail"] = position["shares"]
            self.state["day"] = day
            self.state["quotes"].update(payload["quotes"])
            for order in self.state["orders"].values():
                self._match(order)
            return self.snapshot()

        return self._mutate(update)

    def _executable(self, request: dict[str, Any], quote: dict[str, Any]) -> bool:
        price = float(quote.get("price", 0))
        if price <= 0:
            return False
        order_time = str(request.get("time") or "")
        if order_time and self.state["day"]:
            if datetime.datetime.fromisoformat(order_time).date().isoformat() > self.state["day"]:
                return False
        limit = float(request.get("price", 0))
        if request["side"] == "buy":
            return (not limit or price <= limit) and price < quote.get("up_limit", float("inf"))
        return (not limit or price >= limit) and price > quote.get("down_limit", 0)

    def _match(self, order: dict[str, Any]) -> None:
        if order["status"] not in {"open", "partial"}:
            return
        request = order["request"]
        quote = self.state["quotes"].get(request["asset"], {})
        if not self._executable(request, quote):
            return
        shares = min(request["shares"] - order["filled"], quote.get("available_shares", 1e20))
        if shares <= 0:
            return
        self._fill(order, shares, float(quote["price"]))
        if "available_shares" in quote:
            quote["available_shares"] -= shares

    def _fill(self, order: dict[str, Any], shares: float, price: float) -> None:
        request = order["request"]
        amount = shares * price
        fee = amount * self.state["commission"]
        if request["side"] == "sell":
            fee += amount * self.state["stamp_tax"]
        self._update_account(request, shares, price, fee)
        order["filled"] += shares
        order["status"] = "filled" if order["filled"] == request["shares"] else "partial"
        self.state["sequence"] += 1
        self.state["trades"].append(
            {
                "trade_id": str(self.state["sequence"]),
                "order_id": order["order_id"],
                "asset": request["asset"],
                "side": request["side"],
                "shares": shares,
                "price": price,
                "amount": amount,
                "fee": fee,
                "date": self.state["day"],
            }
        )

    def _update_account(
        self, request: dict[str, Any], shares: float, price: float, fee: float
    ) -> None:
        symbol = request["asset"]
        amount = shares * price
        if request["side"] == "buy":
            if amount + fee > self.state["cash"]:
                raise ValueError("Insufficient cash")
            position = self.state["positions"].setdefault(
                symbol, {"shares": 0, "avail": 0, "price": 0}
            )
            position["price"] = (position["shares"] * position["price"] + amount + fee) / (
                position["shares"] + shares
            )
            position["shares"] += shares
            self.state["cash"] -= amount + fee
        else:
            position = self.state["positions"][symbol]
            if shares > position["avail"]:
                raise ValueError("Insufficient available position")
            position["shares"] -= shares
            position["avail"] -= shares
            self.state["cash"] += amount - fee
            if not position["shares"]:
                del self.state["positions"][symbol]

    def cancel(self, identity: str) -> dict[str, Any]:
        """Cancel only the unfilled remainder, retaining immutable fill history."""

        def update() -> dict[str, Any]:
            order = self.state["orders"][identity]
            if order["status"] != "filled":
                order["status"] = "cancelled"
            return copy.deepcopy(order)

        return self._mutate(update)

    def snapshot(self) -> dict[str, Any]:
        """Return a consistent account and reconciliation view."""
        with self._lock:
            state = copy.deepcopy(self.state)
        state["market_value"] = sum(
            position["shares"] * state["quotes"].get(symbol, {}).get("price", position["price"])
            for symbol, position in state["positions"].items()
        )
        state["total"] = state["cash"] + state["market_value"]
        return state
