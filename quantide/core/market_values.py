"""Normalization of scalar values received from market-data publishers."""

import datetime
from typing import Any


def float_or_none(value: Any) -> float | None:
    """Parse an optional numeric quote field without inventing a zero price."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def datetime_or_none(value: Any) -> datetime.datetime | None:
    """Parse an ISO timestamp from persisted or bus payloads."""
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
