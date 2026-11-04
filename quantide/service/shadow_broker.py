"""dry-run 影子 broker：使用回测撮合口径（当前支持 auction_close/close）。"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import polars as pl

from quantide.core.enums import BrokerKind, FrameType, OrderSide
from quantide.core.errors import (
    InsufficientCash,
    InsufficientPosition,
    NonMultipleOfLotSize,
)
from quantide.core.ports.broker import ExecutionResult
from quantide.data.models import Asset, Position, Trade
from quantide.data.models.daily_bars import daily_bars
from quantide.service.bar_views import HistBarView


class ShadowBroker:
    """只用于 dry-run 的轻量回测撮合账户。"""

    def __init__(
        self,
        *,
        portfolio_id: str,
        principal: float,
        config: dict[str, Any],
        trade_date: datetime.date,
        cash: float | None = None,
        positions: list[dict[str, Any]] | None = None,
        portfolio_name: str = "dry-run-shadow",
    ) -> None:
        self.portfolio_id = portfolio_id
        self.portfolio_name = portfolio_name
        self.status = True
        self.kind = BrokerKind.SIMULATION
        self._principal = float(principal)
        self._cash = float(cash if cash is not None else principal)
        self._trade_date = trade_date
        self._config = dict(config or {})
        self._positions: dict[str, Position] = {}
        self._price_cache: dict[str, float] = {}
        self._open_cache: dict[str, float] = {}
        self._limit_cache: dict[str, tuple[float, float]] = {}
        self._bar_view = HistBarView(daily_bars)

        def _cfg_float(key: str, default: float) -> float:
            value = config.get(key)
            if value is None or value == "":
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        self._commission = _cfg_float("commission", 1e-4)
        self._stamp_tax = _cfg_float("stamp_duty", 5e-4)
        self._transfer_fee = _cfg_float("transfer_fee", 1e-5)
        self._min_commission = _cfg_float("min_commission", 5.0)
        self._slippage = _cfg_float("slippage_pct", 0.001)
        self._auction_epsilon = _cfg_float("auction_epsilon", 0.001)
        self.trades: list[dict[str, Any]] = []
        for item in positions or []:
            try:
                self._positions[str(item["asset"])] = Position(
                    portfolio_id=portfolio_id,
                    dt=trade_date,
                    asset=str(item["asset"]),
                    shares=float(item.get("shares") or 0),
                    avail=float(item.get("avail") or 0),
                    price=float(item.get("price") or 0),
                    profit=0.0,
                    mv=float(item.get("mv") or 0),
                )
            except Exception:
                continue

    # ------------------------------------------------------------------
    # 账户/数据接口
    # ------------------------------------------------------------------
    def settle_t1(self) -> None:
        for position in self._positions.values():
            position.avail = position.shares

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def principal(self) -> float:
        return self._principal

    @property
    def positions(self) -> dict[str, Position]:
        for asset, position in list(self._positions.items()):
            price = self._close_price(asset)
            if price > 0:
                position.mv = position.shares * price
                position.profit = position.mv - position.shares * position.price
            if position.shares <= 0:
                self._positions.pop(asset, None)
        return self._positions

    @property
    def total_assets(self) -> float:
        return self._cash + sum(p.mv for p in self.positions.values())

    @property
    def asset(self) -> Asset:
        market_value = sum(p.mv for p in self.positions.values())
        return Asset(
            portfolio_id=self.portfolio_id,
            dt=self._trade_date,
            principal=self._principal,
            cash=self._cash,
            frozen_cash=0.0,
            market_value=market_value,
            total=self._cash + market_value,
        )

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        return {asset: self._close_price(asset) for asset in assets}

    def get_bars_range(
        self,
        assets: list[str] | None,
        start_dt: datetime.datetime | datetime.date,
        end_dt: datetime.datetime | datetime.date | None = None,
        adjust: str | None = None,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        return self._bar_view.get_bars_range(
            assets, start_dt, end_dt, adjust=adjust, include_forming_bar=False
        )

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: FrameType | str = "1d",
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        return self._bar_view.get_history(
            asset, count, end_dt, frame_type, include_forming_bar=False
        )

    def record(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_clock(self, *args: Any, **kwargs: Any) -> None:
        return None

    def write_backtest_log(self, *args: Any, **kwargs: Any) -> None:
        return None

    # ------------------------------------------------------------------
    # 撮合
    # ------------------------------------------------------------------
    def _close_price(self, asset: str) -> float:
        if asset in self._price_cache:
            return self._price_cache[asset]
        price = 0.0
        try:
            frame = daily_bars.get_bars_in_range(
                self._trade_date,
                self._trade_date,
                assets=[asset],
                adjust=None,
                eager_mode=True,
            )
            if isinstance(frame, pl.LazyFrame):
                frame = frame.collect()
            if frame is not None and not frame.is_empty():
                price = float(frame.row(0, named=True).get("close") or 0)
                limits = frame.row(0, named=True)
                self._open_cache[asset] = float(limits.get("open") or 0)
                self._limit_cache[asset] = (
                    float(limits.get("down_limit") or 0),
                    float(limits.get("up_limit") or 0),
                )
        except Exception:
            price = 0.0
        self._price_cache[asset] = price
        return price

    def _execution_reference_price(self, asset: str) -> float:
        """Use the target day's open only for next-open shadow orders."""
        self._close_price(asset)
        if str(self._config.get("fill_timing", "")).lower() in {
            "next_open",
            "open",
        }:
            return self._open_cache.get(asset, 0.0)
        return self._price_cache.get(asset, 0.0)

    def _limits(self, asset: str) -> tuple[float, float]:
        if asset not in self._limit_cache:
            self._close_price(asset)
        return self._limit_cache.get(asset, (0.0, 0.0))

    def _fee(self, amount: float, side: OrderSide) -> float:
        commission = max(self._min_commission, amount * self._commission)
        transfer = amount * self._transfer_fee
        stamp = amount * self._stamp_tax if side == OrderSide.SELL else 0.0
        return commission + transfer + stamp

    def _fill_price(self, asset: str, side: OrderSide, limit_price: float = 0.0) -> float:
        reference = self._execution_reference_price(asset)
        if reference <= 0:
            return 0.0
        down_limit, up_limit = self._limits(asset)
        if side == OrderSide.BUY and up_limit > 0 and reference >= up_limit:
            return 0.0
        if side == OrderSide.SELL and down_limit > 0 and reference <= down_limit:
            return 0.0
        if limit_price > 0:
            if side == OrderSide.BUY and limit_price < reference:
                return 0.0
            if side == OrderSide.SELL and limit_price > reference:
                return 0.0
            return float(limit_price)
        direction = 1.0 if side == OrderSide.BUY else -1.0
        return round(reference * (1.0 + self._slippage * direction), 4)

    def _lot_shares(self, shares: float) -> int:
        value = int(float(shares) // 100) * 100
        if value <= 0:
            raise NonMultipleOfLotSize("shadow", float(shares))
        return value

    def _record_trade(
        self,
        asset: str,
        side: OrderSide,
        shares: int,
        price: float,
        fee: float,
    ) -> Trade:
        trade = Trade(
            portfolio_id=self.portfolio_id,
            tid=uuid.uuid4().hex,
            qtoid=uuid.uuid4().hex,
            foid="shadow",
            asset=asset,
            shares=shares,
            price=price,
            amount=price * shares,
            tm=datetime.datetime.combine(self._trade_date, datetime.time(15, 0)),
            side=side,
            cid="shadow",
            fee=fee,
        )
        self.trades.append(
            {
                "date": self._trade_date.isoformat(),
                "asset": asset,
                "side": side.value,
                "shares": shares,
                "price": price,
                "amount": trade.amount,
                "fee": fee,
            }
        )
        return trade

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        shares = self._lot_shares(shares)
        fill = self._fill_price(asset, OrderSide.BUY, float(price or 0))
        if fill <= 0:
            return ExecutionResult.empty()
        amount = fill * shares
        fee = self._fee(amount, OrderSide.BUY)
        if amount + fee > self._cash:
            raise InsufficientCash(asset, amount + fee, self._cash)
        self._cash -= amount + fee
        position = self._positions.get(asset)
        if position is None:
            position = Position(
                portfolio_id=self.portfolio_id,
                dt=self._trade_date,
                asset=asset,
                shares=0,
                avail=0,
                price=0,
                profit=0.0,
                mv=0.0,
            )
            self._positions[asset] = position
        total_shares = position.shares + shares
        position.price = (
            (position.shares * position.price + amount + fee) / total_shares
            if total_shares > 0
            else fill
        )
        position.shares = total_shares
        position.mv = total_shares * fill
        trade = self._record_trade(asset, OrderSide.BUY, shares, fill, fee)
        return ExecutionResult(qt_oid=uuid.uuid4().hex, trades=[trade])

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        shares = self._lot_shares(shares)
        position = self._positions.get(asset)
        if position is None or position.avail < shares:
            raise InsufficientPosition(security=asset, amount=shares)
        fill = self._fill_price(asset, OrderSide.SELL, float(price or 0))
        if fill <= 0:
            return ExecutionResult.empty()
        amount = fill * shares
        fee = self._fee(amount, OrderSide.SELL)
        self._cash += amount - fee
        position.shares -= shares
        position.avail -= shares
        position.mv = max(0.0, position.shares * fill)
        if position.shares <= 0:
            self._positions.pop(asset, None)
        trade = self._record_trade(asset, OrderSide.SELL, shares, fill, fee)
        return ExecutionResult(qt_oid=uuid.uuid4().hex, trades=[trade])

    async def buy_amount(
        self,
        asset: str,
        amount: int | float,
        price: int | float = 0,
        order_time: datetime.datetime | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        fill = self._execution_reference_price(asset)
        if fill <= 0:
            return ExecutionResult.empty()
        shares = int(float(amount) / fill / 100) * 100
        if shares <= 0:
            return ExecutionResult.empty()
        return await self.buy(asset, shares, price=price, order_time=order_time)

    async def sell_amount(
        self,
        asset: str,
        amount: int | float,
        price: int | float = 0,
        order_time: datetime.datetime | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        position = self.positions.get(asset)
        if position is None:
            return ExecutionResult.empty()
        fill = self._execution_reference_price(asset)
        if fill <= 0:
            return ExecutionResult.empty()
        shares = min(position.avail, int(float(amount) / fill / 100) * 100)
        if shares <= 0:
            return ExecutionResult.empty()
        return await self.sell(asset, shares, price=price, order_time=order_time)


__all__ = ["ShadowBroker"]
