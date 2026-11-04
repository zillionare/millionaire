"""Named configuration for backtest accounting and execution behavior."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from typing import Any, Literal, Self


@dataclass(frozen=True)
class BacktestOptions:
    """Optional broker settings in the established positional argument order."""

    principal: float = 1000000
    commission: float = 0.0001
    stamp_duty: float = 0.0005
    min_commission: float = 5.0
    transfer_fee: float = 1e-05
    portfolio_name: str = "backtest"
    match_level: Literal["day", "minute"] = "day"
    desc: str = ""
    save_logs: bool = False
    risk_overlay: Any | None = None
    auction_epsilon: float = 0.001
    minute_bars: Any | None = None
    allow_same_bar_repurchase: bool = True

    @classmethod
    def resolve(
        cls, positional: Sequence[Any], configured: Self | None, overrides: Mapping[str, Any]
    ) -> Self:
        """Preserve legacy positional/keyword calls while supporting named configuration."""
        names = [field.name for field in fields(cls)]
        if len(positional) > len(names):
            raise TypeError("Too many positional backtest options")
        values = dict(zip(names, positional, strict=False))
        repeated = values.keys() & overrides.keys()
        if repeated:
            raise TypeError(f"Multiple values for backtest options: {sorted(repeated)}")
        values.update(overrides)
        return cls(**values) if configured is None else replace(configured, **values)
