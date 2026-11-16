"""Common account facts used by overview and account management."""

from dataclasses import dataclass


@dataclass
class AccountFacts:
    """Identity and accounting totals shared by account read models."""

    account_id: str
    account_name: str
    mode: str
    strategy_id: str | None
    total_assets: float
    available_cash: float
    market_value: float
    account_pnl: float
    daily_pnl: float
    hidden: bool
    status: str
