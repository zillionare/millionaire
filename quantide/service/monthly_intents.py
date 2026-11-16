"""Durable cross-month order intents for 1M strategies."""

from __future__ import annotations

import datetime
import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from filelock import FileLock

from quantide.config.paths import get_app_config_dir
from quantide.core.atomic_files import atomic_path, read_json_dict
from quantide.core.market_time import market_now
from quantide.core.order_identity import client_order_id


class MonthlyIntentStore:
    """Small durable JSON intent ledger keyed by signal and strategy."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        payload = read_json_dict(self.path)
        payload.setdefault("pending", {})
        payload.setdefault("completed", {})
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with atomic_path(self.path) as temporary:
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def seen(self, key: str) -> bool:
        with self._lock, FileLock(str(self.path) + ".lock", timeout=10):
            payload = self._read()
            return key in payload["pending"] or key in payload["completed"]

    def enqueue(self, intent: dict[str, Any]) -> bool:
        key = str(intent["key"])
        with self._lock, FileLock(str(self.path) + ".lock", timeout=10):
            payload = self._read()
            if key in payload["pending"] or key in payload["completed"]:
                return False
            intent = dict(intent)
            intent["created_at"] = market_now().isoformat()
            payload["pending"][key] = intent
            self._write(payload)
            return True

    def complete(self, key: str) -> None:
        with self._lock, FileLock(str(self.path) + ".lock", timeout=10):
            payload = self._read()
            intent = payload["pending"].pop(key, None)
            if intent is not None:
                intent["completed_at"] = market_now().isoformat()
                payload["completed"][key] = intent
                self._write(payload)

    def pending(self) -> list[dict[str, Any]]:
        with self._lock, FileLock(str(self.path) + ".lock", timeout=10):
            return list(self._read()["pending"].values())

    def due(self, day: datetime.date, *, namespace: str | None = None) -> list[dict[str, Any]]:
        intents = []
        for intent in self.pending():
            if namespace is not None and intent.get("namespace") != namespace:
                continue
            try:
                execute_date = datetime.date.fromisoformat(str(intent.get("execute_date", "")))
            except ValueError:
                continue
            if execute_date <= day:
                intents.append(intent)
        return sorted(intents, key=lambda item: str(item.get("execute_date", "")))

    def clear(self) -> None:
        with self._lock, FileLock(str(self.path) + ".lock", timeout=10):
            self._write({"pending": {}, "completed": {}})


def intent_namespace(
    lifecycle: str,
    account_id: str,
    strategy: str,
    version: str,
    params: dict[str, Any],
) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"{lifecycle}:{account_id}:{strategy}:{version}:{digest}"


def intent_key(namespace: str, asset: str, signal_date: datetime.date, direction: str) -> str:
    payload = f"{namespace}|{asset}|{signal_date.isoformat()}|{direction}"
    return hashlib.sha256(payload.encode()).hexdigest()


def position_shares(broker: Any, asset: str) -> float:
    positions = getattr(broker, "positions", None)
    if isinstance(positions, dict):
        position = positions.get(asset)
        return float(getattr(position, "shares", 0) or 0)
    for position in positions or []:
        if getattr(position, "asset", "") == asset:
            return float(getattr(position, "shares", 0) or 0)
    return 0.0


async def execute_intent(
    broker: Any, intent: dict[str, Any], *, order_time: datetime.datetime
) -> Any:
    """Submit one durable intent with its key as the broker-side order identity."""
    token = client_order_id.set(str(intent.get("order_id") or intent["key"]))
    try:
        price = float(intent.get("price", 0) or 0)
        asset = str(intent["asset"])
        if intent["direction"] == "buy":
            if intent.get("shares"):
                return await broker.buy(
                    asset, float(intent["shares"]), price=price, order_time=order_time
                )
            return await broker.buy_amount(
                asset, float(intent["amount"]), price=price, order_time=order_time
            )
        shares = float(intent.get("shares") or position_shares(broker, asset))
        if shares <= 0:
            return None
        return await broker.sell(asset, shares, price=price, order_time=order_time)
    finally:
        client_order_id.reset(token)


def _default_store() -> MonthlyIntentStore:
    return MonthlyIntentStore(get_app_config_dir() / "monthly-intents.json")


monthly_intent_store = _default_store()
