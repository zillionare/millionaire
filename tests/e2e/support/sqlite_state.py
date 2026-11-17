"""Preserve the process-wide SQLite singleton across isolated app sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantide.data.sqlite import db


@dataclass(frozen=True)
class SQLiteState:
    """The observable database binding before an isolated session starts."""

    initialized: bool
    db_path: str


def capture_sqlite_state() -> SQLiteState:
    """Capture the singleton path/state before a session rebinds it."""
    return SQLiteState(
        initialized=bool(getattr(db, "_initialized", False)),
        db_path=str(getattr(db, "db_path", "") or ""),
    )


def restore_sqlite_state(state: SQLiteState) -> None:
    """Restore or clear the singleton so no deleted temporary path survives."""
    db.close()
    db._initialized = False
    restorable = state.db_path == ":memory:" or (
        bool(state.db_path) and Path(state.db_path).is_file()
    )
    if state.initialized and restorable:
        db.init(state.db_path)
        return
    db.db_path = ""
    db.__dict__.pop("_connection_uri", None)


__all__ = ["SQLiteState", "capture_sqlite_state", "restore_sqlite_state"]
