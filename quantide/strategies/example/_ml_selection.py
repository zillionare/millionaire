"""Validated settings for the ML example's one-shot selection API."""

import datetime
from dataclasses import dataclass
from typing import Any

from quantide.strategies.example._ml_support import (
    _coerce_date,
    _future_return_horizon,
    _parse_custom_assets,
)


@dataclass(frozen=True)
class SelectionOptions:
    """The ranking settings shared by loading, candidate filtering and model fitting."""

    top_k: int
    universe_size: int
    train_window: int
    horizon: int
    use_lightgbm: bool
    universe_mode: str
    trim_pct: float
    custom_assets: list[str] | None
    as_of: datetime.date | None

    @classmethod
    def from_config(
        cls,
        cfg: dict[str, Any],
        overrides: dict[str, Any] | None,
        as_of: datetime.date | datetime.datetime | str | None,
    ) -> "SelectionOptions":
        top_k = max(1, int(cfg.get("top_k", 5)))
        return cls(
            top_k=top_k,
            universe_size=max(top_k, int(cfg.get("universe_size", 2000))),
            train_window=max(10, int(cfg.get("train_window", 45))),
            horizon=_future_return_horizon(overrides or cfg),
            use_lightgbm=bool(cfg.get("use_lightgbm", True)),
            universe_mode=str(cfg.get("universe_mode", "market_cap_trim")).strip(),
            trim_pct=min(0.5, max(0.0, float(cfg.get("market_cap_trim_pct", 0.05)))),
            custom_assets=_parse_custom_assets(cfg),
            as_of=_coerce_date(as_of),
        )
