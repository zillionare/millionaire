"""Shared semantic colors for account, order and position views."""


def trade_side_text(side: str | None) -> str:
    """Return the A-share buy/sell text color."""
    return "text-red-600" if side == "买入" else "text-green-600"


def profit_text(value: float) -> str:
    """Return the A-share gain/loss text color."""
    return "text-red-600" if value >= 0 else "text-green-600"


def account_badge(is_live: bool) -> str:
    """Return the badge color for an account's execution type."""
    return "bg-red-100 text-red-700" if is_live else "bg-gray-100 text-gray-700"


def user_status_badge(active: bool) -> str:
    """Return the badge color for an enabled or disabled user."""
    return "bg-green-100 text-green-800" if active else "bg-red-100 text-red-800"
