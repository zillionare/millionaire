"""Independent realized and mark-to-market performance attribution oracle."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any, Literal

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class AuditTrade:
    asset: str
    side: Side
    shares: float
    price: float
    fee: float = 0.0
    tax: float = 0.0


@dataclass(frozen=True)
class AttributionPeriod:
    start_equity: float
    start_positions: dict[str, float]
    start_prices: dict[str, float]
    end_prices: dict[str, float]
    trades: tuple[AuditTrade, ...] = ()
    external_flow: float = 0.0
    dividends: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class _NormalizedTrade:
    asset: str
    direction: float
    shares: float
    price: float
    fee: float
    tax: float
    end_price: float


@dataclass(frozen=True)
class PeriodAttribution:
    start_equity: float
    end_equity: float
    external_flow: float
    delta_equity: float
    start_cash: float
    end_cash: float
    start_positions: dict[str, float]
    end_positions: dict[str, float]
    price_pnl: float
    execution_pnl: float
    costs: float
    dividends: float
    residual: float
    contributions: dict[str, float]
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    observed_end_equity: float | None = None
    observed_end_cash: float | None = None
    reconciliation_gap: float = 0.0
    reconciliation_issues: tuple[str, ...] = ()

    @property
    def return_pct(self) -> float:
        return self.delta_equity / self.start_equity if self.start_equity else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_equity": self.start_equity,
            "end_equity": self.end_equity,
            "external_flow": self.external_flow,
            "delta_equity": self.delta_equity,
            "start_cash": self.start_cash,
            "end_cash": self.end_cash,
            "start_positions": self.start_positions,
            "end_positions": self.end_positions,
            "price_pnl": self.price_pnl,
            "execution_pnl": self.execution_pnl,
            "costs": self.costs,
            "dividends": self.dividends,
            "residual": self.residual,
            "contributions": self.contributions,
            "return_pct": self.return_pct,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "observed_end_equity": self.observed_end_equity,
            "observed_end_cash": self.observed_end_cash,
            "reconciliation_gap": self.reconciliation_gap,
            "reconciliation_issues": list(self.reconciliation_issues),
        }


def _finite(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _prices(positions: dict[str, float], prices: dict[str, float], label: str) -> None:
    for asset, shares in positions.items():
        if shares > 0 and asset not in prices:
            raise ValueError(f"{label} price missing for {asset}")
        if shares < 0:
            raise ValueError(f"{label} position is negative for {asset}")
        if asset in prices and _finite(prices[asset], f"{label} price") <= 0:
            raise ValueError(f"{label} price must be positive for {asset}")


def _start_state(period: AttributionPeriod) -> tuple[float, dict[str, float], float]:
    start_equity = _finite(period.start_equity, "start_equity")
    if start_equity <= 0:
        raise ValueError("start_equity must be positive")
    start_positions = {
        asset: _finite(shares, "shares")
        for asset, shares in period.start_positions.items()
        if shares != 0
    }
    _prices(start_positions, period.start_prices, "start")
    _prices(start_positions, period.end_prices, "end")
    start_value = sum(
        shares * float(period.start_prices[asset]) for asset, shares in start_positions.items()
    )
    start_cash = start_equity - start_value
    if start_cash < -1e-9:
        raise ValueError("start positions exceed start equity")
    return start_equity, start_positions, start_cash


def _normalize_trade(trade: AuditTrade, end_prices: dict[str, float]) -> _NormalizedTrade:
    shares = _finite(trade.shares, "trade shares")
    price = _finite(trade.price, "trade price")
    if shares <= 0 or price <= 0:
        raise ValueError("trade shares and price must be positive")
    if trade.side not in ("buy", "sell"):
        raise ValueError("trade side must be buy or sell")
    fee = _finite(trade.fee, "fee")
    tax = _finite(trade.tax, "tax")
    if fee < 0 or tax < 0:
        raise ValueError("fee and tax must be non-negative")
    if trade.asset not in end_prices:
        raise ValueError(f"end price missing for {trade.asset}")
    end_price = float(end_prices[trade.asset])
    if end_price <= 0:
        raise ValueError("end price must be positive")
    return _NormalizedTrade(
        trade.asset,
        1.0 if trade.side == "buy" else -1.0,
        shares,
        price,
        fee,
        tax,
        end_price,
    )


def _apply_trades(
    period: AttributionPeriod,
    start_positions: dict[str, float],
    start_cash: float,
) -> tuple[dict[str, float], float, float, float, dict[str, float]]:
    end_positions = dict(start_positions)
    end_cash = start_cash
    execution_pnl = 0.0
    costs = 0.0
    contributions: dict[str, float] = {}
    for trade in period.trades:
        item = _normalize_trade(trade, period.end_prices)
        end_positions[item.asset] = (
            end_positions.get(item.asset, 0.0) + item.direction * item.shares
        )
        if end_positions[item.asset] < -1e-9:
            raise ValueError(f"trade sells more than held for {item.asset}")
        end_cash -= item.direction * item.shares * item.price + item.fee + item.tax
        costs -= item.fee + item.tax
        trade_pnl = item.direction * item.shares * (item.end_price - item.price)
        execution_pnl += trade_pnl
        contributions[item.asset] = (
            contributions.get(item.asset, 0.0) + trade_pnl - item.fee - item.tax
        )
    return end_positions, end_cash, execution_pnl, costs, contributions


def _price_contributions(
    period: AttributionPeriod,
    start_positions: dict[str, float],
    contributions: dict[str, float],
) -> float:
    price_pnl = 0.0
    for asset, shares in start_positions.items():
        value = shares * (float(period.end_prices[asset]) - float(period.start_prices[asset]))
        price_pnl += value
        contributions[asset] = contributions.get(asset, 0.0) + value
    return price_pnl


def _apply_income(
    period: AttributionPeriod,
    end_positions: dict[str, float],
    end_cash: float,
    contributions: dict[str, float],
) -> tuple[float, float]:
    dividend_total = 0.0
    for asset, amount in period.dividends.items():
        value = _finite(amount, "dividend")
        if value < 0:
            raise ValueError("dividend must be non-negative")
        if end_positions.get(asset, 0.0) <= 0:
            raise ValueError(f"dividend requires a held position for {asset}")
        dividend_total += value
        contributions[asset] = contributions.get(asset, 0.0) + value
    end_cash += _finite(period.external_flow, "external_flow") + dividend_total
    if end_cash < -1e-9:
        raise ValueError("trades and costs exceed cash")
    return end_cash, dividend_total


def _end_state(
    period: AttributionPeriod,
    end_positions: dict[str, float],
    end_cash: float,
) -> tuple[dict[str, float], float, float]:
    filtered = {asset: shares for asset, shares in end_positions.items() if abs(shares) > 1e-12}
    _prices(filtered, period.end_prices, "end")
    end_value = sum(shares * float(period.end_prices[asset]) for asset, shares in filtered.items())
    return filtered, end_value, end_cash + end_value


def attribute_period(period: AttributionPeriod) -> PeriodAttribution:
    start_equity, start_positions, start_cash = _start_state(period)
    end_positions, end_cash, execution_pnl, costs, contributions = _apply_trades(
        period, start_positions, start_cash
    )
    price_pnl = _price_contributions(period, start_positions, contributions)
    end_cash, dividends = _apply_income(period, end_positions, end_cash, contributions)
    end_positions, end_value, end_equity = _end_state(period, end_positions, end_cash)
    delta = end_equity - start_equity - period.external_flow
    explained = price_pnl + execution_pnl + costs + dividends
    return PeriodAttribution(
        start_equity=start_equity,
        end_equity=end_equity,
        external_flow=period.external_flow,
        delta_equity=delta,
        start_cash=start_cash,
        end_cash=end_cash,
        start_positions=start_positions,
        end_positions=end_positions,
        price_pnl=price_pnl,
        execution_pnl=execution_pnl,
        costs=costs,
        dividends=dividends,
        residual=delta - explained,
        contributions={asset: value for asset, value in contributions.items() if value != 0},
        observed_end_equity=end_equity,
        observed_end_cash=end_cash,
    )


def link_carino(periods: list[PeriodAttribution]) -> dict[str, Any]:
    if not periods:
        raise ValueError("at least one period is required")
    returns = [period.return_pct for period in periods]
    if any(value <= -1 for value in returns):
        raise ValueError("period return must be greater than -1")
    total = math.prod(1.0 + value for value in returns) - 1.0
    if total <= -1:
        raise ValueError("total return must be greater than -1")
    total_factor = 1.0 if abs(total) < 1e-12 else math.log1p(total) / total
    linked: dict[str, float] = {}
    residual = 0.0
    for period in periods:
        factor = (
            1.0
            if abs(period.return_pct) < 1e-12
            else math.log1p(period.return_pct) / period.return_pct
        )
        residual += factor * period.residual / period.start_equity
        for asset, contribution in period.contributions.items():
            linked[asset] = linked.get(asset, 0.0) + factor * contribution / period.start_equity
    linked = {asset: value / total_factor for asset, value in linked.items()}
    residual /= total_factor
    return {
        "period_returns": returns,
        "total_return": total,
        "linked_contributions": linked,
        "linked_residual": residual,
        "linked_sum": sum(linked.values()) + residual,
    }
