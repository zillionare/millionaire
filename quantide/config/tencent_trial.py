"""One opt-in, non-renewable 30-day demonstration window for Tencent data."""

import datetime
from dataclasses import dataclass

from quantide.data.sqlite import db

TRIAL_DAYS = 30
SCHEMA = """
CREATE TABLE IF NOT EXISTS tencent_trial (
    id INTEGER PRIMARY KEY CHECK (id=1),
    enabled INTEGER NOT NULL DEFAULT 0,
    first_enabled_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    expired INTEGER NOT NULL DEFAULT 0
)
"""


@dataclass(frozen=True)
class TrialStatus:
    """Persisted opt-in and immutable deadline, expressed in UTC."""

    enabled: bool = False
    first_enabled_at: str = ""
    expires_at: str = ""
    expired: bool = False


def _utc(now: datetime.datetime | None = None) -> datetime.datetime:
    current = now or datetime.datetime.now(datetime.UTC)
    if current.tzinfo is None:
        raise ValueError("Tencent trial clock must be timezone-aware")
    return current.astimezone(datetime.UTC)


def trial_status(now: datetime.datetime | None = None) -> TrialStatus:
    """Enforce expiry on every use, including after application restart."""
    if not db._initialized:
        return TrialStatus()
    connection = db.db.conn
    connection.execute(SCHEMA)
    row = connection.execute(
        "SELECT enabled, first_enabled_at, expires_at, expired FROM tencent_trial WHERE id=1"
    ).fetchone()
    if row is None:
        return TrialStatus()
    enabled, first, deadline, expired = row
    expired = bool(expired) or _utc(now) >= datetime.datetime.fromisoformat(deadline)
    if expired and enabled:
        with connection:
            connection.execute("UPDATE tencent_trial SET enabled=0, expired=1 WHERE id=1")
    return TrialStatus(bool(enabled) and not expired, first, deadline, expired)


def configure_trial(enabled: bool, now: datetime.datetime | None = None) -> TrialStatus:
    """Opt in once; disabling, reinstalling code or rerunning wizard cannot renew it."""
    if not db._initialized:
        raise RuntimeError("Initialize the application database before configuring data sources")
    current = _utc(now)
    connection = db.db.conn
    connection.execute(SCHEMA)
    with connection:
        if enabled:
            connection.execute(
                "INSERT OR IGNORE INTO tencent_trial "
                "(id, enabled, first_enabled_at, expires_at) VALUES (1, 0, ?, ?)",
                (current.isoformat(), (current + datetime.timedelta(days=TRIAL_DAYS)).isoformat()),
            )
        connection.execute("UPDATE tencent_trial SET enabled=? WHERE id=1", (int(enabled),))
    status = trial_status(current)
    if enabled and status.expired:
        raise ValueError("腾讯行情演示期已结束；请通过扩展接入其它行情实现")
    return status


def require_tencent_access() -> None:
    """Gate every HTTP request; environment flags never bypass the deadline."""
    if not trial_status().enabled:
        raise PermissionError("腾讯行情默认关闭或演示期已结束；可在初始化向导启用一次 30 天演示")
