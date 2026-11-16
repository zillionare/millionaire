"""Interval token normalization that keeps monthly and minute bars distinct."""

from __future__ import annotations


def normalize_interval(value: object) -> str:
    """Preserve uppercase ``1M`` for monthly bars; lowercase all other tokens."""
    raw = str(value).strip()
    if raw == "1M":
        return "1M"
    return raw.lower()
