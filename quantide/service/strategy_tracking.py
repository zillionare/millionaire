"""dry-run 影子与仿真/实盘对照的每日快照。"""

from __future__ import annotations

import datetime
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from quantide.config.output_paths import external_runtime_path
from quantide.config.paths import get_app_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_tracking_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    runtime_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    nav REAL NOT NULL DEFAULT 0,
    cash REAL NOT NULL DEFAULT 0,
    market_value REAL NOT NULL DEFAULT 0,
    positions TEXT NOT NULL DEFAULT '[]',
    trades TEXT NOT NULL DEFAULT '[]',
    model_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(runtime_id, date, source)
);
CREATE TABLE IF NOT EXISTS strategy_shadow_state (
    runtime_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    cash REAL NOT NULL,
    positions TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_tracking_runs (
    runtime_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    backtest_id TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL,
    fill_timing TEXT NOT NULL DEFAULT 'auction_close',
    dry_run_enabled INTEGER NOT NULL DEFAULT 1,
    last_tracking_date TEXT NOT NULL DEFAULT '',
    last_retrain_date TEXT NOT NULL DEFAULT '',
    gap_dates TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_next_open_intents (
    intent_id TEXT PRIMARY KEY,
    intent_key TEXT NOT NULL,
    runtime_id TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL DEFAULT '',
    signal_date TEXT NOT NULL,
    target_date TEXT NOT NULL,
    signal_bar TEXT NOT NULL DEFAULT '',
    target_bar TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '[]',
    kwargs TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT '',
    UNIQUE(runtime_id, intent_key)
);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


class TrackingStore:
    """SQLite 跟踪存储；与主库共用应用数据库文件。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = external_runtime_path(path) if path else get_app_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def rebind(self, path: str | Path) -> None:
        """Move the process-wide store after the app config override is set."""
        self.path = external_runtime_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Own both the transaction and connection; SQLite's context alone stays open."""
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(strategy_next_open_intents)"
                ).fetchall()
            }
            # The tracking database predates intraday next-open intents.  Keep
            # existing 1d rows valid while adding the bar identity in place.
            for column in ("signal_bar", "target_bar"):
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE strategy_next_open_intents "
                        f"ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                    )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_next_open_target_bar "
                "ON strategy_next_open_intents(status, target_bar)"
            )

    def ensure_run(
        self,
        runtime_id: str,
        portfolio_id: str,
        *,
        backtest_id: str = "",
        start_date: datetime.date | None = None,
        fill_timing: str = "auction_close",
        dry_run_enabled: bool = True,
    ) -> None:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        start = (start_date or datetime.date.today()).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_tracking_runs
                (runtime_id, portfolio_id, backtest_id, start_date, fill_timing,
                 dry_run_enabled, last_tracking_date, last_retrain_date, gap_dates, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '', '', '[]', ?)
                ON CONFLICT(runtime_id) DO UPDATE SET
                    portfolio_id=excluded.portfolio_id,
                    fill_timing=excluded.fill_timing,
                    dry_run_enabled=excluded.dry_run_enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    runtime_id,
                    portfolio_id,
                    backtest_id,
                    start,
                    fill_timing,
                    1 if dry_run_enabled else 0,
                    now,
                ),
            )

    def update_run(self, runtime_id: str, **updates: Any) -> None:
        fields: list[str] = []
        params: list[Any] = []
        for key in (
            "backtest_id",
            "start_date",
            "fill_timing",
            "dry_run_enabled",
            "last_tracking_date",
            "last_retrain_date",
            "gap_dates",
        ):
            if key in updates:
                value = updates[key]
                if key in {"gap_dates"}:
                    value = _json(value)
                if key == "dry_run_enabled":
                    value = 1 if value else 0
                fields.append(f"{key}=?")
                params.append(value)
        if not fields:
            return
        fields.append("updated_at=?")
        params.append(datetime.datetime.now().isoformat(timespec="seconds"))
        params.append(runtime_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE strategy_tracking_runs SET {', '.join(fields)} WHERE runtime_id=?",
                params,
            )

    def get_run(self, runtime_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM strategy_tracking_runs WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["gap_dates"] = _load_json(data.get("gap_dates"), [])
        data["dry_run_enabled"] = bool(data.get("dry_run_enabled"))
        return data

    def list_runs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM strategy_tracking_runs ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["gap_dates"] = _load_json(data.get("gap_dates"), [])
            data["dry_run_enabled"] = bool(data.get("dry_run_enabled"))
            result.append(data)
        return result

    def save_shadow_state(
        self,
        runtime_id: str,
        portfolio_id: str,
        *,
        cash: float,
        positions: list[dict[str, Any]],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_shadow_state
                (runtime_id, portfolio_id, cash, positions, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(runtime_id) DO UPDATE SET
                    portfolio_id=excluded.portfolio_id,
                    cash=excluded.cash,
                    positions=excluded.positions,
                    updated_at=excluded.updated_at
                """,
                (
                    runtime_id,
                    portfolio_id,
                    float(cash),
                    _json(positions),
                    datetime.datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def get_shadow_state(self, runtime_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM strategy_shadow_state WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["positions"] = _load_json(data.get("positions"), [])
        return data

    def save_daily(
        self,
        *,
        runtime_id: str,
        portfolio_id: str,
        day: datetime.date | str,
        source: str,
        nav: float,
        cash: float,
        market_value: float,
        positions: list[dict[str, Any]],
        trades: list[dict[str, Any]] | None = None,
        model_hash: str = "",
    ) -> None:
        date_text = day.isoformat() if isinstance(day, datetime.date) else str(day)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_tracking_daily
                (runtime_id, portfolio_id, date, source, nav, cash, market_value,
                 positions, trades, model_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runtime_id, date, source) DO UPDATE SET
                    nav=excluded.nav,
                    cash=excluded.cash,
                    market_value=excluded.market_value,
                    positions=excluded.positions,
                    trades=excluded.trades,
                    model_hash=excluded.model_hash,
                    created_at=excluded.created_at
                """,
                (
                    runtime_id,
                    portfolio_id,
                    date_text,
                    source,
                    float(nav),
                    float(cash),
                    float(market_value),
                    _json(positions),
                    _json(trades or []),
                    model_hash,
                    datetime.datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def list_daily(
        self,
        runtime_id: str | None = None,
        portfolio_id: str | None = None,
        *,
        source: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if runtime_id:
            clauses.append("runtime_id=?")
            params.append(runtime_id)
        if portfolio_id:
            clauses.append("portfolio_id=?")
            params.append(portfolio_id)
        if source:
            clauses.append("source=?")
            params.append(source)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM strategy_tracking_daily {where} ORDER BY date ASC LIMIT ?",
                params,
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["positions"] = _load_json(data.get("positions"), [])
            data["trades"] = _load_json(data.get("trades"), [])
            result.append(data)
        return result

    def latest_daily(self, runtime_id: str, source: str) -> dict[str, Any] | None:
        rows = self.list_daily(runtime_id=runtime_id, source=source, limit=1)
        return rows[-1] if rows else None

    def enqueue_next_open_intent(
        self,
        *,
        runtime_id: str,
        portfolio_id: str,
        strategy_id: str,
        signal_date: datetime.date,
        target_date: datetime.date,
        method: str,
        args: list[Any] | tuple[Any, ...],
        kwargs: dict[str, Any],
        intent_key: str,
        signal_bar: datetime.datetime | None = None,
        target_bar: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        """Insert an intent once and return the durable row on every retry."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_next_open_intents
                (intent_id, intent_key, runtime_id, portfolio_id, strategy_id,
                 signal_date, target_date, signal_bar, target_bar, method, args, kwargs,
                 status, error, created_at, processed_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?, '')
                 ON CONFLICT(runtime_id, intent_key) DO NOTHING
                """,
                (
                    uuid.uuid5(uuid.NAMESPACE_URL, f"{runtime_id}:next_open:{intent_key}").hex,
                    intent_key,
                    runtime_id,
                    portfolio_id,
                    strategy_id,
                    signal_date.isoformat(),
                    target_date.isoformat(),
                    self._bar_text(signal_bar),
                    self._bar_text(target_bar),
                    method,
                    _json(list(args)),
                    _json(kwargs),
                    datetime.datetime.now().isoformat(timespec="seconds"),
                ),
            )
            row = connection.execute(
                "SELECT * FROM strategy_next_open_intents WHERE runtime_id=? AND intent_key=?",
                (runtime_id, intent_key),
            ).fetchone()
        if row is None:  # pragma: no cover - protected by the transaction
            raise RuntimeError("无法持久化 next_open intent")
        return self._intent_row(row)

    def list_next_open_intents(
        self,
        *,
        runtime_id: str | None = None,
        target_date: datetime.date | None = None,
        target_bar: datetime.datetime | None = None,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        clauses = ["status=?"]
        params: list[Any] = [status]
        if runtime_id:
            clauses.append("runtime_id=?")
            params.append(runtime_id)
        if target_date is not None:
            clauses.append("target_date<=?")
            params.append(target_date.isoformat())
        if target_bar is not None:
            clauses.append("target_bar != '' AND target_bar<=?")
            params.append(self._bar_text(target_bar))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM strategy_next_open_intents WHERE "
                + " AND ".join(clauses)
                + " ORDER BY target_date, created_at, intent_id",
                params,
            ).fetchall()
        return [self._intent_row(row) for row in rows]

    def mark_next_open_intent(self, intent_id: str, *, status: str, error: str = "") -> None:
        processed_at = datetime.datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "UPDATE strategy_next_open_intents SET status=?, error=?, processed_at=? "
                "WHERE intent_id=?",
                (status, error, processed_at, intent_id),
            )

    def claim_next_open_intent(self, intent_id: str) -> dict[str, Any] | None:
        """Atomically reserve a pending intent for one submitter.

        A row left in ``processing`` after a crash is intentionally not
        reclaimed automatically: the external broker may already have
        accepted it, so resubmitting would violate the no-duplicate contract.
        """
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE strategy_next_open_intents SET status='processing' "
                "WHERE intent_id=? AND status='pending'",
                (intent_id,),
            )
            if updated.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM strategy_next_open_intents WHERE intent_id=?",
                (intent_id,),
            ).fetchone()
        return self._intent_row(row) if row is not None else None

    @staticmethod
    def _intent_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["args"] = _load_json(result.get("args"), [])
        result["kwargs"] = _load_json(result.get("kwargs"), {})
        return result

    @staticmethod
    def _bar_text(value: datetime.datetime | None) -> str:
        if value is None:
            return ""
        if not isinstance(value, datetime.datetime):
            raise TypeError("bar identity must be a datetime")
        # Runtime bar boundaries are local, timezone-naive datetimes.  Strip
        # tzinfo so ordering remains lexical and consistent after restart.
        return value.replace(tzinfo=None).isoformat(timespec="seconds")


tracking_store = TrackingStore()

__all__ = ["TrackingStore", "tracking_store"]
