"""Decode parameters from persisted strategy/backtest information."""

import json
from typing import Any


def stored_strategy_config(info: object) -> dict[str, Any]:
    """Read direct dictionaries and legacy JSON config envelopes."""
    if isinstance(info, dict):
        return info
    if not isinstance(info, str) or not info:
        return {}
    try:
        payload = json.loads(info)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    config = payload.get("config")
    return config if isinstance(config, dict) else payload
