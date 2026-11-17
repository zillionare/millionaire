"""L1 hand-calculated oracle for the teaching single-asset weight cap."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "quantide"
    / "assets"
    / "examples"
    / "risk_single_asset_cap.py"
)
MODULE = ModuleType("risk_single_asset_cap_oracle")
MODULE.__file__ = str(TEMPLATE)
exec(compile(TEMPLATE.read_text(encoding="utf-8"), str(TEMPLATE), "exec"), MODULE.__dict__)


class _Broker:
    def __init__(self, equity: float, price: float, held: dict[str, int] | None = None) -> None:
        self._equity = equity
        self._price = price
        self.positions = {
            asset: SimpleNamespace(shares=shares) for asset, shares in (held or {}).items()
        }

    def risk_total_equity(self) -> float:
        return self._equity

    def risk_reference_price(self, asset: str, order_time, price: float = 0) -> float:
        return price or self._price


def _cap(broker: _Broker, shares: int) -> int:
    return MODULE.capped_buy_shares(broker, "000001.SZ", shares, 0.0, None, 0.25)


def test_existing_holding_consumes_the_per_asset_budget() -> None:
    # 1,000,000 * 25% = 250,000 cap; 1,000 held * 100 = 100,000 used;
    # remaining 150,000 / 100 = 1,500 shares, below the requested 3,000.
    assert _cap(_Broker(1_000_000, 100, {"000001.SZ": 1_000}), 3_000) == 1_500


def test_cap_rounds_down_to_whole_lots_after_budget_division() -> None:
    # 250,000 / 33.33 = 7,500.75 shares; whole lots -> 7,500.
    assert _cap(_Broker(1_000_000, 33.33), 7_654) == 7_500


def test_requested_quantity_is_floored_to_whole_lots() -> None:
    assert _cap(_Broker(1_000_000, 10), 155) == 100


def test_holding_above_cap_blocks_the_open() -> None:
    # 3,000 * 100 = 300,000 already above the 250,000 cap -> zero shares.
    assert _cap(_Broker(1_000_000, 100, {"000001.SZ": 3_000}), 1_000) == 0


def test_zero_explicit_price_uses_broker_reference_price() -> None:
    # 100,000 * 25% = 25,000; 25,000 / 50 = 500 shares.
    assert _cap(_Broker(100_000, 50), 1_000) == 500
