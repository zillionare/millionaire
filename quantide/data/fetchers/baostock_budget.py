"""Durable, process-safe quota and freeze evidence for BaoStock history requests."""

import datetime
import json
from pathlib import Path
from typing import Any, cast

from filelock import FileLock

from quantide.core.atomic_files import write_json
from quantide.core.market_time import market_now


class BaostockThrottledError(RuntimeError):
    """A request cannot proceed within the source quota or freeze policy."""


class BaostockBudget:
    """Reserve requests before networking; a crash never refunds a reservation."""

    def __init__(self, path: str | Path, limit: int) -> None:
        self.path = Path(path)
        self.limit = min(int(limit), 45000)
        if self.limit <= 0:
            raise ValueError("BaoStock daily budget must be positive")

    def _load(self) -> dict[str, Any]:
        now = market_now()
        state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        if state.get("day") != now.date().isoformat():
            state.update(day=now.date().isoformat(), used=0)
        if state.get("year") != now.year:
            state.update(year=now.year, freezes=0)
        return cast(dict[str, Any], state)

    def _locked(self) -> FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return FileLock(str(self.path) + ".transaction.lock", timeout=60)

    def status(self) -> dict[str, Any]:
        with self._locked():
            return self._load()

    def _require_available(self, state: dict[str, Any]) -> None:
        until = state.get("blocked_until")
        if until and market_now() < datetime.datetime.fromisoformat(until):
            raise BaostockThrottledError(f"BaoStock 黑名单冻结/冷却期至 {until}")
        if state.get("used", 0) >= self.limit:
            raise BaostockThrottledError(f"BaoStock 今日请求预算已用尽（上限 {self.limit}）")

    def check(self) -> None:
        with self._locked():
            self._require_available(self._load())

    def consume(self) -> None:
        with self._locked():
            state = self._load()
            self._require_available(state)
            state["used"] = state.get("used", 0) + 1
            write_json(self.path, state)

    def freeze(self) -> str:
        with self._locked():
            state = self._load()
            state["freezes"] = state.get("freezes", 0) + 1
            state["blocked_until"] = (
                market_now() + datetime.timedelta(hours=6 * state["freezes"], minutes=5)
            ).isoformat()
            write_json(self.path, state)
            return str(state["blocked_until"])
