"""Small discoverable ML lifecycle strategy for the supported 30m path.

This example intentionally makes no trading decision.  It exercises strategy
initialisation, completed-bar history, feature construction, and shutdown
without requiring a large training panel.  LightGBM is a hard dependency for
the strategy.
"""

from __future__ import annotations

import datetime
from typing import Any

import polars as pl

from quantide.core.enums import FrameType
from quantide.core.strategy import BaseStrategy

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover - exercised in minimal installations
    lgb = None  # type: ignore[assignment]


class LightGBM30mSmokeStrategy(BaseStrategy):
    """Discoverable, deterministic 30m strategy lifecycle smoke target."""

    BAR_INTERVAL = "30m"
    PARAMS: dict[str, Any] = {
        "symbols": ["000001.SZ"],
        "bar_interval": "30m",
        "fill_timing": "cheat_on_close",
    }
    params = PARAMS

    @staticmethod
    def default_config() -> dict[str, Any]:
        return dict(LightGBM30mSmokeStrategy.PARAMS)

    def __init__(self, broker: Any, config: dict[str, Any] | None = None) -> None:
        super().__init__(broker, {**self.default_config(), **(config or {})})
        if lgb is None:
            raise RuntimeError(
                "LightGBM30mSmokeStrategy requires the lightgbm package; "
                "install the project's ml30m optional dependency before running it"
            )
        self.engine = "lightgbm"
        self.completed_bars = 0
        self.last_score: float | None = None

    async def init(self) -> None:
        self.log("30m smoke engine={}", self.engine)

    async def on_bar(self, tm: datetime.datetime) -> None:
        """Consume only bars closed at ``tm``; do not use a forming bar."""
        symbols = self.config.get("symbols") or self.config.get("universe") or []
        if isinstance(symbols, str):
            symbols = [symbols]
        for asset in symbols:
            bars = self.get_bars(
                str(asset),
                count=2,
                end_dt=tm,
                frame_type=FrameType.MIN30,
                include_forming_bar=False,
            )
            if bars is None or bars.is_empty() or len(bars) < 2:
                continue
            self.last_score = self._score(bars)
            self.completed_bars += 1

    def _score(self, bars: pl.DataFrame) -> float:
        """Return a one-step LightGBM score."""
        closes = bars.sort("date")["close"].cast(pl.Float64).to_list()
        if self.engine == "lightgbm":
            # A tiny fixed model keeps this example lifecycle-focused while
            # still verifying the declared LightGBM dependency when available.
            model = lgb.LGBMRegressor(n_estimators=4, max_depth=2, learning_rate=0.1, verbosity=-1)
            model.fit([[0.0], [1.0]], [0.0, closes[-1] - closes[-2]])
            return float(model.predict([[1.0]])[0])
        raise RuntimeError(f"Unsupported model engine: {self.engine}")


__all__ = ["LightGBM30mSmokeStrategy"]
