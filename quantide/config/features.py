"""Edition feature gates.

The shared runtime contains adapters used by private editions as well as the
Community Edition (CE).  Keep the edition decision in one small module so CE
does not accidentally expose or start a private-only capability while the
generic gateway implementation remains available to future editions.
"""

from __future__ import annotations

from quantide.config.branding import get_runtime_edition

CE_EDITION = "millionaire"
LIVE_TRADING_UNAVAILABLE_MESSAGE = "CE edition 暂不支持实盘交易"


class FeatureUnavailableError(RuntimeError):
    """Raised when an edition does not include a requested feature."""


def supports_live_trading() -> bool:
    """Return whether the active edition includes live trading."""
    return get_runtime_edition() != CE_EDITION


def live_trading_unavailable_message() -> str:
    """Return the stable user-facing live-trading unavailable message."""
    return LIVE_TRADING_UNAVAILABLE_MESSAGE


def require_live_trading() -> None:
    """Raise a clear error when live trading is unavailable in this edition."""
    if not supports_live_trading():
        raise FeatureUnavailableError(LIVE_TRADING_UNAVAILABLE_MESSAGE)


__all__ = [
    "CE_EDITION",
    "FeatureUnavailableError",
    "LIVE_TRADING_UNAVAILABLE_MESSAGE",
    "live_trading_unavailable_message",
    "require_live_trading",
    "supports_live_trading",
]
