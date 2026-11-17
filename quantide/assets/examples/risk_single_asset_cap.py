"""Teaching cap; no stop-loss/drawdown/triple barrier; copied only when enabled."""

import datetime
from functools import partial
from typing import Any

from quantide.core.strategy import RiskStrategy
from quantide.service.risk_programs import RiskProgramAdapter, RiskProgramRegistry

PROGRAM_ID = "example.single_asset_weight_cap"
DEFAULT_MAX_WEIGHT = 0.25


def _held_shares(broker: Any, asset: str) -> float:
    positions = broker.positions
    if isinstance(positions, dict):
        position = positions.get(asset)
    else:
        position = next((item for item in positions if item.asset == asset), None)
    return float(getattr(position, "shares", 0.0) or 0.0)


def capped_buy_shares(
    broker: Any,
    asset: str,
    shares: int | float,
    price: float,
    order_time: datetime.datetime | None,
    max_weight: float,
) -> int:
    requested = int(shares) // 100 * 100
    reference = float(price or broker.risk_reference_price(asset, order_time, price))
    equity = float(broker.risk_total_equity())
    if requested <= 0 or reference <= 0 or equity <= 0:
        return 0
    budget = max(0.0, max_weight * equity - _held_shares(broker, asset) * reference)
    return max(0, min(requested, int(budget / reference / 100) * 100))


def _guard(max_weight: float) -> Any:
    return partial(capped_buy_shares, max_weight=max_weight)


class SingleAssetWeightCapOverlay:
    def __init__(self, params: dict[str, Any]) -> None:
        self.max_weight = float(params.get("max_weight", DEFAULT_MAX_WEIGHT))

    async def check_open(self, broker: Any, tm: datetime.datetime) -> None:
        broker.set_buy_guard(PROGRAM_ID, _guard(self.max_weight))

    async def check_intraday(self, broker: Any, tm: datetime.datetime) -> None: ...

    def sync_positions(self, positions: Any, today: datetime.date) -> None: ...


class SingleAssetWeightCapLive(RiskStrategy):
    def __init__(self, broker: Any, config: dict[str, Any]) -> None:
        super().__init__(broker, config)
        self.max_weight = float(config.get("max_weight", DEFAULT_MAX_WEIGHT))

    async def on_check(self, positions: dict[str, Any], tm: datetime.datetime) -> None:
        self.broker.set_buy_guard(  # type: ignore[attr-defined]
            self.risk_strategy_id, _guard(self.max_weight)
        )

    async def on_stop(self) -> None:
        self.broker.clear_buy_guard(self.risk_strategy_id)  # type: ignore[attr-defined]


def register_extensions(registry: RiskProgramRegistry) -> None:
    registry.register(
        RiskProgramAdapter(
            id=PROGRAM_ID,
            name="单标的买入权重上限（教学示例）",
            description="按总权益限制单标的买入后市值，按 100 股整手截断。",
            default_params={"max_weight": DEFAULT_MAX_WEIGHT},
            overlay_factory=SingleAssetWeightCapOverlay,
            live_strategy_factory=SingleAssetWeightCapLive,
        )
    )
