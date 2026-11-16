"""Durable factor-tracking run ledger with leases and cooperative cancellation."""

from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from filelock import FileLock
from loguru import logger

from quantide.core.market_time import market_now

PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
INSUFFICIENT = "insufficient"
CANCELLED = "cancelled"
INTERRUPTED = "interrupted"
SUPERSEDED = "superseded"
ACTIVE = (PENDING, RUNNING)
TERMINAL = (SUCCEEDED, FAILED, INSUFFICIENT, CANCELLED, INTERRUPTED, SUPERSEDED)


@dataclass(frozen=True)
class RunBudget:
    max_seconds: float = 900.0
    lease_seconds: float = 60.0
    max_attempts: int = 2
    max_factors: int = 64

    def __post_init__(self) -> None:
        if self.max_seconds <= 0 or self.lease_seconds <= 0:
            raise ValueError("run budget must be positive")
        if self.max_attempts < 1 or self.max_factors < 1:
            raise ValueError("run budget counts must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_seconds": self.max_seconds,
            "lease_seconds": self.lease_seconds,
            "max_attempts": self.max_attempts,
            "max_factors": self.max_factors,
        }


@dataclass(frozen=True)
class FactorRun:
    run_id: str
    idempotency_key: str
    scope: str
    factor_ids: tuple[str, ...]
    lookback: str
    status: str
    owner: str
    phase: str
    checkpoint: dict[str, Any] = field(default_factory=dict)
    attempt: int = 0
    source_revision: int = 0
    profile_revisions: dict[str, int] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    cancel_requested: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "idempotency_key": self.idempotency_key,
            "scope": self.scope,
            "factor_ids": list(self.factor_ids),
            "lookback": self.lookback,
            "status": self.status,
            "owner": self.owner,
            "phase": self.phase,
            "checkpoint": self.checkpoint,
            "attempt": self.attempt,
            "source_revision": self.source_revision,
            "profile_revisions": self.profile_revisions,
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
        }


def idempotency_key(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


class RunFence:
    """Owner/lease check plus the lock shared with the final snapshot commit."""

    def __init__(self, store: FactorRunStore, run_id: str, owner: str) -> None:
        self.store = store
        self.run_id = run_id
        self.owner = owner

    @property
    def lock_path(self) -> str:
        return str(self.store.path) + ".fence.lock"

    def __call__(self) -> bool:
        return self.store.owns(self.run_id, self.owner)


class FactorRunStore:
    """SQLite-backed run queue safe for threads and processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _fence(self) -> FileLock:
        return FileLock(str(self.path) + ".fence.lock", timeout=30)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS factor_runs (
                    run_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    factor_ids TEXT NOT NULL,
                    lookback TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL DEFAULT '',
                    lease_until REAL NOT NULL DEFAULT 0,
                    phase TEXT NOT NULL DEFAULT '',
                    checkpoint TEXT NOT NULL DEFAULT '{}',
                    attempt INTEGER NOT NULL DEFAULT 0,
                    source_revision INTEGER NOT NULL DEFAULT 0,
                    profile_revisions TEXT NOT NULL DEFAULT '{}',
                    payload TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS factor_runs_status
                    ON factor_runs(status, created_at);
                CREATE INDEX IF NOT EXISTS factor_runs_key
                    ON factor_runs(idempotency_key);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(factor_runs)").fetchall()
            }
            for name, definition in (
                ("payload", "TEXT NOT NULL DEFAULT '{}'"),
                ("result", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE factor_runs ADD COLUMN {name} {definition}")

    @staticmethod
    def _row(row: sqlite3.Row) -> FactorRun:
        return FactorRun(
            run_id=row["run_id"],
            idempotency_key=row["idempotency_key"],
            scope=row["scope"],
            factor_ids=tuple(json.loads(row["factor_ids"])),
            lookback=row["lookback"],
            status=row["status"],
            owner=row["owner"],
            phase=row["phase"],
            checkpoint=json.loads(row["checkpoint"] or "{}"),
            attempt=int(row["attempt"]),
            source_revision=int(row["source_revision"]),
            profile_revisions=json.loads(row["profile_revisions"] or "{}"),
            payload=json.loads(row["payload"] or "{}"),
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    def _supersede(
        self,
        connection: sqlite3.Connection,
        factors: tuple[str, ...],
        source_revision: int,
        stamp: str,
        *,
        scope: str,
    ) -> None:
        active_rows = connection.execute(
            "SELECT run_id, scope, factor_ids, source_revision "
            "FROM factor_runs WHERE status IN (?, ?)",
            ACTIVE,
        ).fetchall()
        tracking_scopes = {"factor", "group"}
        for row in active_rows:
            same_scope = row["scope"] == scope or (
                row["scope"] in tracking_scopes and scope in tracking_scopes
            )
            existing = set(json.loads(row["factor_ids"]))
            if (
                same_scope
                and existing.intersection(factors)
                and int(row["source_revision"]) <= source_revision
            ):
                connection.execute(
                    "UPDATE factor_runs SET status = ?, finished_at = ? WHERE run_id = ?",
                    (SUPERSEDED, stamp, row["run_id"]),
                )

    @staticmethod
    def _insert(
        connection: sqlite3.Connection,
        factors: tuple[str, ...],
        key: str,
        lookback: str,
        source_revision: int,
        profile_revisions: dict[str, int],
        stamp: str,
        *,
        scope: str = "",
        payload: dict[str, Any] | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO factor_runs (run_id, idempotency_key, scope, factor_ids, "
            "lookback, status, source_revision, profile_revisions, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                key,
                scope or ("group" if len(factors) > 1 else "factor"),
                json.dumps(list(factors)),
                lookback,
                PENDING,
                source_revision,
                json.dumps(profile_revisions),
                json.dumps(payload or {}),
                stamp,
            ),
        )
        return run_id

    def enqueue(
        self,
        factor_ids: Iterable[str],
        *,
        lookback: str,
        profile_revisions: dict[str, int],
        source_revision: int,
        source_versions: dict[str, Any],
        budget: RunBudget,
        now: datetime.datetime | None = None,
    ) -> list[str]:
        with self._fence():
            factors = tuple(sorted(set(factor_ids)))[: budget.max_factors]
            if not factors:
                return []
            key = idempotency_key(
                {
                    "factors": factors,
                    "lookback": lookback,
                    "profiles": {factor: profile_revisions.get(factor, 0) for factor in factors},
                    "sources": source_versions,
                }
            )
            stamp = (now or market_now()).isoformat()
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                active = connection.execute(
                    "SELECT run_id FROM factor_runs WHERE status IN (?, ?) AND idempotency_key = ?",
                    (*ACTIVE, key),
                ).fetchone()
                if active:
                    connection.commit()
                    return []
                self._supersede(
                    connection,
                    factors,
                    source_revision,
                    stamp,
                    scope="group" if len(factors) > 1 else "factor",
                )
                run_id = self._insert(
                    connection,
                    factors,
                    key,
                    lookback,
                    source_revision,
                    profile_revisions,
                    stamp,
                )
                connection.commit()
            return [run_id]

    def enqueue_task(
        self,
        *,
        scope: str,
        factor_ids: Iterable[str],
        lookback: str,
        payload: dict[str, Any],
        budget: RunBudget,
        now: datetime.datetime | None = None,
    ) -> str:
        with self._fence():
            factors = tuple(sorted(set(factor_ids)))[: budget.max_factors]
            if not factors:
                raise ValueError("task requires at least one factor")
            key = idempotency_key({"scope": scope, "factors": factors, "payload": payload})
            stamp = (now or market_now()).isoformat()
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT run_id FROM factor_runs WHERE idempotency_key = ? AND status IN (?, ?)",
                    (key, *ACTIVE),
                ).fetchone()
                if existing is not None:
                    connection.commit()
                    return str(existing["run_id"])
                run_id = self._insert(
                    connection,
                    factors,
                    key,
                    lookback,
                    0,
                    {},
                    stamp,
                    scope=scope,
                    payload=payload,
                )
                connection.commit()
            return run_id

    def set_result(self, run_id: str, result: dict[str, Any], *, owner: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE factor_runs SET result = ? "
                "WHERE run_id = ? AND owner = ? AND status = ? AND lease_until > ?",
                (json.dumps(result, default=str), run_id, owner, RUNNING, time.time()),
            )
            connection.commit()
            return cursor.rowcount > 0

    def get(self, run_id: str) -> FactorRun | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM factor_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._row(row) if row is not None else None

    def claim(
        self,
        owner: str,
        *,
        budget: RunBudget,
        scopes: tuple[str, ...] | None = None,
        now: datetime.datetime | None = None,
    ) -> FactorRun | None:
        with self._fence():
            stamp = (now or market_now()).isoformat()
            now_seconds = time.time()
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE factor_runs SET status = ?, owner = '', lease_until = 0 "
                    "WHERE status = ? AND lease_until < ? AND attempt < ?",
                    (PENDING, RUNNING, now_seconds, budget.max_attempts),
                )
                connection.execute(
                    "UPDATE factor_runs SET status = ?, finished_at = ? "
                    "WHERE status = ? AND lease_until < ?",
                    (INTERRUPTED, stamp, RUNNING, now_seconds),
                )
                scope_clause = ""
                parameters: tuple[Any, ...] = (PENDING,)
                if scopes:
                    placeholders = ", ".join("?" for _ in scopes)
                    scope_clause = f" AND scope IN ({placeholders})"
                    parameters += scopes
                row = connection.execute(
                    "SELECT * FROM factor_runs WHERE status = ?"
                    + scope_clause
                    + " ORDER BY created_at, run_id LIMIT 1",
                    parameters,
                ).fetchone()
                if row is not None and int(row["attempt"]) >= budget.max_attempts:
                    connection.execute(
                        "UPDATE factor_runs SET status = ?, error = ?, finished_at = ? "
                        "WHERE run_id = ?",
                        (FAILED, "attempt budget exhausted", stamp, row["run_id"]),
                    )
                    connection.commit()
                    return None
                if row is not None:
                    connection.execute(
                        "UPDATE factor_runs SET status = ?, owner = ?, lease_until = ?, "
                        "attempt = attempt + 1, started_at = ? WHERE run_id = ?",
                        (
                            RUNNING,
                            owner,
                            now_seconds + budget.lease_seconds,
                            stamp,
                            row["run_id"],
                        ),
                    )
                    connection.commit()
                    claimed = connection.execute(
                        "SELECT * FROM factor_runs WHERE run_id = ?", (row["run_id"],)
                    ).fetchone()
                    return self._row(claimed) if claimed is not None else None
                connection.commit()
            return None

    def checkpoint(
        self,
        run_id: str,
        owner: str,
        *,
        phase: str,
        checkpoint: dict[str, Any],
        lease_seconds: float,
    ) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE factor_runs SET phase = ?, checkpoint = ?, lease_until = ? "
                "WHERE run_id = ? AND owner = ? AND status = ?",
                (
                    phase,
                    json.dumps(checkpoint, default=str),
                    time.time() + lease_seconds,
                    run_id,
                    owner,
                    RUNNING,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def owns(self, run_id: str, owner: str) -> bool:
        """Return whether this owner still holds an uncancelled, unexpired lease."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM factor_runs WHERE run_id = ? AND owner = ? AND status = ? "
                "AND lease_until > ? AND cancel_requested = 0",
                (run_id, owner, RUNNING, time.time()),
            ).fetchone()
        return row is not None

    def touch(self, run_id: str, owner: str, lease_seconds: float) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE factor_runs SET lease_until = ? "
                "WHERE run_id = ? AND owner = ? AND status = ?",
                (time.time() + lease_seconds, run_id, owner, RUNNING),
            )
            connection.commit()
            return cursor.rowcount > 0

    def finish(self, run_id: str, owner: str, status: str, error: str = "") -> bool:
        if status not in TERMINAL:
            raise ValueError("invalid terminal run status")
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE factor_runs SET status = ?, error = ?, finished_at = ? "
                "WHERE run_id = ? AND owner = ? AND status = ? AND lease_until > ?",
                (
                    status,
                    error,
                    market_now().isoformat(),
                    run_id,
                    owner,
                    RUNNING,
                    time.time(),
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def release_owner(self, owner: str) -> int:
        with self._fence():
            """Fence a stopped worker and make its unfinished runs claimable again."""
            with self._connection() as connection:
                cursor = connection.execute(
                    "UPDATE factor_runs SET status = ?, owner = '', lease_until = 0, "
                    "finished_at = '' WHERE owner = ? AND status = ?",
                    (PENDING, owner, RUNNING),
                )
                connection.commit()
                return cursor.rowcount

    def request_cancel(self, run_id: str) -> bool:
        with self._fence():
            with self._connection() as connection:
                pending = connection.execute(
                    "UPDATE factor_runs SET status = ?, finished_at = ? "
                    "WHERE run_id = ? AND status = ?",
                    (CANCELLED, market_now().isoformat(), run_id, PENDING),
                )
                running = connection.execute(
                    "UPDATE factor_runs SET cancel_requested = 1 WHERE run_id = ? AND status = ?",
                    (run_id, RUNNING),
                )
                connection.commit()
                return pending.rowcount + running.rowcount > 0

    def cancel_factors(self, factor_ids: Iterable[str]) -> list[str]:
        targets = set(factor_ids)
        cancelled: list[str] = []
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id, factor_ids FROM factor_runs WHERE status IN (?, ?)",
                ACTIVE,
            ).fetchall()
        for row in rows:
            if targets.intersection(json.loads(row["factor_ids"])):
                self.request_cancel(row["run_id"])
                cancelled.append(row["run_id"])
        return cancelled

    def cancelled(self, run_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM factor_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return bool(row["cancel_requested"]) if row is not None else True

    def recover(self) -> int:
        with self._fence():
            with self._connection() as connection:
                cursor = connection.execute(
                    "UPDATE factor_runs SET status = ?, owner = '', lease_until = 0, "
                    "finished_at = '' WHERE status = ? AND lease_until < ?",
                    (PENDING, RUNNING, time.time()),
                )
                connection.commit()
                return cursor.rowcount

    def list_runs(self, *, status: str | None = None, limit: int = 100) -> list[FactorRun]:
        query = "SELECT * FROM factor_runs"
        parameters: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters += (limit,)
        with self._connection() as connection:
            return [self._row(row) for row in connection.execute(query, parameters).fetchall()]


def _heartbeat_loop(
    store: FactorRunStore,
    run_id: str,
    owner: str,
    budget: RunBudget,
    cancel: threading.Event,
    stop: threading.Event,
) -> None:
    interval = max(0.01, min(0.1, budget.lease_seconds / 3))
    lease_interval = max(interval, budget.lease_seconds / 3)
    touched = time.monotonic()
    while not stop.wait(interval):
        if store.cancelled(run_id):
            cancel.set()
            return
        if time.monotonic() - touched < lease_interval:
            continue
        if not store.touch(run_id, owner, budget.lease_seconds):
            cancel.set()
            return
        touched = time.monotonic()


def _checkpoint_writer(
    store: FactorRunStore,
    run_id: str,
    owner: str,
    budget: RunBudget,
    cancel: threading.Event,
) -> Callable[[str, dict[str, Any]], bool]:
    def checkpoint(phase: str, payload: dict[str, Any]) -> bool:
        if store.cancelled(run_id):
            cancel.set()
        return store.checkpoint(
            run_id,
            owner,
            phase=phase,
            checkpoint=payload,
            lease_seconds=budget.lease_seconds,
        )

    return checkpoint


Executor = Callable[[FactorRun, threading.Event, Callable[[str, dict[str, Any]], bool]], str]


class FactorRunWorker:
    """Bounded worker pool that claims persisted runs and executes one at a time."""

    def __init__(
        self,
        store: FactorRunStore,
        executor: Executor,
        *,
        budget: RunBudget | None = None,
        concurrency: int = 2,
        poll_seconds: float = 0.05,
        scopes: tuple[str, ...] | None = None,
    ) -> None:
        self.store = store
        self.executor = executor
        self.scopes = scopes
        self.budget = budget or RunBudget()
        self.concurrency = max(1, concurrency)
        self.poll_seconds = poll_seconds
        self.owner = uuid.uuid4().hex
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._active: dict[str, threading.Event] = {}

    def start(self) -> None:
        with self._lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            self._stop.clear()
            self._threads = [
                threading.Thread(target=self._loop, daemon=True, name=f"factor-run-{index}")
                for index in range(self.concurrency)
            ]
            for thread in self._threads:
                thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        deadline = time.monotonic() + timeout
        while any(thread.is_alive() for thread in self._threads):
            with self._lock:
                active = list(self._active.values())
            for event in active:
                event.set()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            for thread in self._threads:
                if thread.is_alive():
                    thread.join(timeout=min(0.05, remaining))
        self.store.release_owner(self.owner)
        self.store.recover()

    def _loop(self) -> None:
        while not self._stop.is_set():
            run = self.store.claim(self.owner, budget=self.budget, scopes=self.scopes)
            if run is None:
                self._stop.wait(self.poll_seconds)
                continue
            if self._stop.is_set():
                self.store.release_owner(self.owner)
                break
            self._execute(run)

    def _execute(self, run: FactorRun) -> None:
        cancel = threading.Event()
        deadline = time.monotonic() + self.budget.max_seconds
        timer = threading.Timer(max(0.0, deadline - time.monotonic()), cancel.set)
        timer.daemon = True
        timer.start()
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=_heartbeat_loop,
            args=(
                self.store,
                run.run_id,
                self.owner,
                self.budget,
                cancel,
                heartbeat_stop,
            ),
            daemon=True,
        )
        heartbeat.start()
        checkpoint = _checkpoint_writer(self.store, run.run_id, self.owner, self.budget, cancel)
        with self._lock:
            self._active[run.run_id] = cancel
        try:
            status = (
                CANCELLED
                if self.store.cancelled(run.run_id)
                else self.executor(run, cancel, checkpoint)
            )
        except InterruptedError:
            status = CANCELLED
        except Exception as exc:
            logger.exception("Factor tracking run failed: {}", run.run_id)
            status = FAILED
            self.store.finish(run.run_id, self.owner, status, f"{type(exc).__name__}: {exc}")
            return
        finally:
            timer.cancel()
            heartbeat_stop.set()
            with self._lock:
                self._active.pop(run.run_id, None)
        if self._stop.is_set() and status == SUCCEEDED:
            status = CANCELLED
        self.store.finish(run.run_id, self.owner, status)
