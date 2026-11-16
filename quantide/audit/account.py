"""Independent double-entry account oracle for audit invariants."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Position:
    shares: float = 0.0
    available: float = 0.0
    cost_basis: float = 0.0
    last_price: float = 0.0


def _positive(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return number


def _nonnegative(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be non-negative and finite")
    return number


@dataclass
class AccountLedger:
    initial_cash: float
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    pending: dict[tuple[dt.date, str], float] = field(default_factory=dict)
    external_flow: float = 0.0
    fees_paid: float = 0.0
    taxes_paid: float = 0.0
    dividends: float = 0.0
    realized_pnl: float = 0.0

    def __post_init__(self) -> None:
        self.initial_cash = _nonnegative(self.initial_cash, "initial_cash")
        self.cash = self.initial_cash

    def _new_position(self, asset: str) -> Position:
        position = self.positions.get(asset)
        if position is None:
            position = Position()
            self.positions[asset] = position
        return position

    def deposit(self, amount: float) -> None:
        value = _positive(amount, "deposit")
        self.cash += value
        self.external_flow += value

    def withdraw(self, amount: float) -> None:
        value = _nonnegative(amount, "withdraw")
        if value > self.cash + 1e-9:
            raise ValueError("withdraw exceeds cash")
        self.cash -= value
        self.external_flow -= value

    def buy(
        self,
        asset: str,
        shares: float,
        price: float,
        trade_date: dt.date,
        settle_date: dt.date,
        *,
        fee: float = 0.0,
    ) -> None:
        quantity = _positive(shares, "shares")
        unit_price = _positive(price, "price")
        commission = _nonnegative(fee, "fee")
        gross = quantity * unit_price
        total = gross + commission
        if total > self.cash + 1e-9:
            raise ValueError("buy exceeds cash")
        if settle_date < trade_date:
            raise ValueError("settle_date precedes trade_date")
        self.cash -= total
        self.fees_paid += commission
        position = self._new_position(asset)
        position.shares += quantity
        position.cost_basis += gross
        position.last_price = unit_price
        key = (settle_date, asset)
        self.pending[key] = self.pending.get(key, 0.0) + quantity

    def settle(self, trading_day: dt.date) -> None:
        ready = [key for key in self.pending if key[0] <= trading_day]
        for settle_date, asset in ready:
            shares = self.pending.pop((settle_date, asset))
            self._new_position(asset).available += shares

    def sell(
        self,
        asset: str,
        shares: float,
        price: float,
        *,
        fee: float = 0.0,
        tax: float = 0.0,
    ) -> None:
        quantity = _positive(shares, "shares")
        unit_price = _positive(price, "price")
        commission = _nonnegative(fee, "fee")
        tax_amount = _nonnegative(tax, "tax")
        position = self.positions.get(asset)
        if position is None or quantity > position.available + 1e-9:
            raise ValueError("sell exceeds available shares")
        if quantity > position.shares + 1e-9:
            raise ValueError("sell exceeds shares")
        average_cost = position.cost_basis / position.shares if position.shares else 0.0
        gross = quantity * unit_price
        cost = average_cost * quantity
        self.cash += gross - commission - tax_amount
        self.fees_paid += commission
        self.taxes_paid += tax_amount
        self.realized_pnl += gross - cost
        position.available -= quantity
        position.shares -= quantity
        position.cost_basis -= cost
        position.last_price = unit_price
        if position.shares <= 1e-12:
            self.positions.pop(asset, None)

    def dividend(self, asset: str, amount: float) -> None:
        value = _nonnegative(amount, "dividend")
        if asset not in self.positions:
            raise ValueError("dividend requires a held position")
        self.cash += value
        self.dividends += value

    def split(self, asset: str, ratio: float) -> None:
        factor = _positive(ratio, "split ratio")
        position = self.positions.get(asset)
        if position is None:
            raise ValueError("split requires a held position")
        position.shares *= factor
        position.available *= factor
        for (settle_date, pending_asset), shares in list(self.pending.items()):
            if pending_asset == asset:
                self.pending[(settle_date, pending_asset)] = shares * factor

    def mark(self, asset: str, price: float) -> None:
        position = self.positions.get(asset)
        if position is None:
            raise KeyError(asset)
        position.last_price = _positive(price, "price")

    def market_value(self) -> float:
        return sum(position.shares * position.last_price for position in self.positions.values())

    def equity(self) -> float:
        return self.cash + self.market_value()

    def snapshot(self, trading_day: dt.date) -> dict[str, Any]:
        value = self.market_value()
        equity = self.cash + value
        positions = {
            asset: {
                "shares": position.shares,
                "available": position.available,
                "cost_basis": position.cost_basis,
                "last_price": position.last_price,
                "market_value": position.shares * position.last_price,
            }
            for asset, position in sorted(self.positions.items())
        }
        weights = {
            asset: item["market_value"] / equity if equity else 0.0
            for asset, item in positions.items()
        }
        return {
            "date": trading_day.isoformat(),
            "cash": self.cash,
            "market_value": value,
            "equity": equity,
            "nav": equity / self.initial_cash if self.initial_cash else 0.0,
            "external_flow": self.external_flow,
            "fees_paid": self.fees_paid,
            "taxes_paid": self.taxes_paid,
            "dividends": self.dividends,
            "realized_pnl": self.realized_pnl,
            "positions": positions,
            "weights": weights,
        }

    def validate(self) -> list[str]:
        errors = []
        if not math.isfinite(self.cash):
            errors.append("cash is not finite")
        if self.cash < -1e-9:
            errors.append("cash is negative")
        for asset, position in self.positions.items():
            if position.shares < -1e-9:
                errors.append(f"{asset}: negative shares")
            if position.available < -1e-9:
                errors.append(f"{asset}: negative available shares")
            if position.available > position.shares + 1e-9:
                errors.append(f"{asset}: available exceeds shares")
            if position.cost_basis < -1e-9:
                errors.append(f"{asset}: negative cost basis")
        return errors
