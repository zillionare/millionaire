"""Versioned raw inputs that invalidate factor tracking snapshots."""

from __future__ import annotations

import datetime
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

from quantide.factors.alpha import FACTOR_VERSION
from quantide.factors.research import STATISTICS_VERSION

SOURCE_FIELDS = (
    "source_market_version",
    "source_calendar_version",
    "source_universe_version",
    "source_dependency_version",
)

_SOURCE_LOCK = threading.RLock()
_SOURCE_TTL_SECONDS = 30.0
_SOURCE_CACHE: tuple[float, dict[str, Any]] | None = None


def _dates_index_path() -> Path:
    from quantide.data.models.daily_bars import daily_bars

    return daily_bars._dates_file_path()


def _store_token() -> tuple[float, str] | None:
    """Use the committed date index instead of walking every partition."""
    try:
        from quantide.data.models.daily_bars import daily_bars

        end = daily_bars.end
        if not isinstance(end, datetime.date):
            return None
        index = _dates_index_path()
        if not index.is_file():
            return None
        return (float(index.stat().st_mtime_ns), end.isoformat())
    except Exception:
        return None


def _market_version(token: tuple[float, str] | None) -> str | None:
    """Read the storage signature maintained beside the daily date index."""
    if token is None:
        return None
    try:
        index = _dates_index_path()
        marker = index.with_suffix(".signature.json")
        signature = str(json.loads(marker.read_text(encoding="utf-8")).get("sha256") or "")
        if marker.stat().st_mtime_ns < index.stat().st_mtime_ns:
            signature = ""
    except Exception:
        signature = ""
    if not signature:
        signature = f"{token[0]:.0f}"
    return f"{signature}:{token[1]}"


def _calendar_version() -> str | None:
    """Version the full authoritative opening calendar, independent of lookback."""
    try:
        from quantide.data.models.calendar import calendar

        frames = calendar.day_frames
        if frames is None or len(frames) == 0:
            return None
        values = [day for day in frames.to_pylist() if isinstance(day, datetime.date)]
        if not values:
            return None
        days = "\n".join(day.isoformat() for day in values)
    except Exception:
        return None
    return "sha256:" + hashlib.sha256(days.encode()).hexdigest()[:16]


def _universe_version() -> str | None:
    """Version the security master and point-in-time index constituents."""
    try:
        from quantide.data import get_index_weight_store
        from quantide.data.models.stocks import stock_list

        assets = sorted(str(asset) for asset in stock_list.data["asset"].to_list())
        if not assets:
            return None
        digest = hashlib.sha256("\n".join(assets).encode())
        digest.update(get_index_weight_store()._storage_signature().encode())
    except Exception:
        return None
    return "sha256:" + digest.hexdigest()[:16]


def _dependency_version() -> str:
    """Bind the factor/statistics source and numeric engine versions."""
    from importlib.metadata import PackageNotFoundError, version

    components = {"factor": FACTOR_VERSION, "statistics": STATISTICS_VERSION}
    for package in ("numpy", "polars", "pyarrow"):
        try:
            components[package] = version(package)
        except PackageNotFoundError:
            components[package] = "missing"
    payload = json.dumps(components, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()[:16]


def source_versions(*, refresh: bool = False) -> dict[str, Any]:
    """Return one snapshot of every raw source version used for invalidation."""
    global _SOURCE_CACHE
    now = time.monotonic()
    if not refresh:
        with _SOURCE_LOCK:
            if _SOURCE_CACHE is not None and now - _SOURCE_CACHE[0] < _SOURCE_TTL_SECONDS:
                return dict(_SOURCE_CACHE[1])
    token = _store_token()
    versions = {
        "source_token": list(token) if token is not None else None,
        "source_market_version": _market_version(token),
        "source_calendar_version": _calendar_version(),
        "source_universe_version": _universe_version(),
        "source_dependency_version": _dependency_version(),
    }
    with _SOURCE_LOCK:
        _SOURCE_CACHE = (now, dict(versions))
    return versions


def source_complete(source: dict[str, Any] | None) -> bool:
    return isinstance(source, dict) and all(
        source.get(field) is not None for field in SOURCE_FIELDS
    )


def source_fields_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        left.get(field) is not None and left.get(field) == right.get(field)
        for field in SOURCE_FIELDS
    )


def source_advanced(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> bool:
    if previous is None or current is None:
        return False
    before = previous.get("source_token")
    after = current.get("source_token")
    if before is not None and after is not None and tuple(after) > tuple(before):
        return True
    return any(previous.get(field) != current.get(field) for field in SOURCE_FIELDS)


def latest_market_day() -> datetime.date | None:
    token = source_versions().get("source_token")
    if token is None:
        return None
    try:
        return datetime.date.fromisoformat(token[1])
    except (IndexError, TypeError, ValueError):
        return None
