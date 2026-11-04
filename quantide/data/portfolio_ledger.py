"""Atomic portfolio snapshots and paper execution commits.

Use sqlite3 directly here: sqlite-utils write helpers commit independently,
which would split a fill from its cash, order and position facts.
"""

import datetime
import sqlite3
from collections.abc import Iterable

from quantide.data.models.base import Entity
from quantide.data.models.entities import Asset, Order, Position, Trade

SNAPSHOT_SCHEMA = """
CREATE TABLE IF NOT EXISTS position_snapshots (
    portfolio_id TEXT NOT NULL,
    dt TEXT NOT NULL,
    PRIMARY KEY (portfolio_id, dt)
)
"""


def _write_entity(connection: sqlite3.Connection, entity: Entity) -> None:
    values = entity.to_dict()
    values = {
        key: value.isoformat() if isinstance(value, datetime.date) else value
        for key, value in values.items()
    }
    columns = ", ".join(f'"{key}"' for key in values)
    placeholders = ", ".join("?" for _ in values)
    keys = entity.__pk__
    keys = [keys] if isinstance(keys, str) else keys
    conflict = ", ".join(f'"{key}"' for key in keys)
    updates = ", ".join(f'"{key}"=excluded."{key}"' for key in values if key not in keys)
    connection.execute(
        f'INSERT INTO "{entity.__table_name__}" ({columns}) VALUES ({placeholders}) '
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}",
        tuple(values.values()),
    )


def _replace_positions(
    connection: sqlite3.Connection,
    portfolio_id: str,
    dt: datetime.date | datetime.datetime,
    positions: Iterable[Position],
) -> None:
    day = dt.date() if isinstance(dt, datetime.datetime) else dt
    connection.execute(
        "DELETE FROM positions WHERE portfolio_id=? AND dt=?",
        (portfolio_id, day.isoformat()),
    )
    for position in positions:
        _write_entity(connection, position)
    connection.execute(
        "INSERT OR REPLACE INTO position_snapshots(portfolio_id, dt) VALUES (?, ?)",
        (portfolio_id, day.isoformat()),
    )


def replace_positions(
    connection: sqlite3.Connection,
    portfolio_id: str,
    dt: datetime.date | datetime.datetime,
    positions: Iterable[Position],
) -> None:
    """Persist even an empty snapshot, retaining historical snapshots."""
    with connection:
        _replace_positions(connection, portfolio_id, dt, positions)


def save_snapshot(
    connection: sqlite3.Connection, asset: Asset, positions: Iterable[Position]
) -> None:
    """Commit cash and the complete position snapshot together."""
    with connection:
        _replace_positions(connection, asset.portfolio_id, asset.dt, positions)
        _write_entity(connection, asset)


def save_execution(
    connection: sqlite3.Connection,
    order: Order,
    trade: Trade,
    asset: Asset,
    positions: Iterable[Position],
) -> None:
    """Commit one fill and all resulting account facts in one transaction."""
    with connection:
        _write_entity(connection, trade)
        _write_entity(connection, order)
        _replace_positions(connection, asset.portfolio_id, asset.dt, positions)
        _write_entity(connection, asset)
