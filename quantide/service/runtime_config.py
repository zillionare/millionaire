"""Runtime configuration coercions shared by deployment and restoration."""

from typing import Any

from quantide.core.market_values import float_or_none as _optional_float


def _float_or(value: Any, default: float) -> float:
    parsed = _optional_float(value)
    return parsed if parsed is not None else default
