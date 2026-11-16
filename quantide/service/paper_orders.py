"""Paper order entry, sizing, cancellation and session settlement."""

from __future__ import annotations

import datetime
from _thread import RLock
from typing import TYPE_CHECKING, Any

from quantide.core.enums import (
    BidType,
    OrderSide,
    OrderStatus,
)
from quantide.core.errors import (
    InsufficientCash,
    InsufficientPosition,
    NonMultipleOfLotSize,
    PriceOutOfLimit,
    TradingHaltedError,
)
from quantide.core.order_identity import client_order_id
from quantide.core.ports.broker import ExecutionResult
from quantide.data.models import Asset, Order, Position, Trade
from quantide.data.models.base import new_uuid_id
from quantide.data.sqlite import db

_IMMEDIATE_FILL_TIMINGS = {"", "close", "cheat_on_close", "auction_close", "auction"}
_PAPER_ORDER_NOOP_OPTIONS = {"strategy_id"}


def _validate_paper_order_options(options: dict[str, Any]) -> None:
    """Reject execution options that the in-process paper matcher cannot honour."""
    unsupported = set(options) - _PAPER_ORDER_NOOP_OPTIONS - {"fill_timing"}
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(f"PaperBroker does not support order options: {names}")
    fill_timing = str(options.get("fill_timing", "")).strip().lower()
    if fill_timing in _IMMEDIATE_FILL_TIMINGS:
        return
    raise ValueError(
        f"PaperBroker does not support fill_timing={fill_timing!r}; "
        "use the durable next-open broker proxy for deferred execution"
    )


def _validate_buy_reference_price(self: PaperOrders, price: float, asset: str) -> float:
    """Validate buying limits and select a conservative sizing reference price."""
    if price != 0:
        down_limit, up_limit = self._get_price_limits(asset)
        if up_limit > 0 and down_limit > 0:
            if price > up_limit or price < down_limit:
                raise PriceOutOfLimit(asset, price, down_limit, up_limit)
    self._reject_at_limit(asset, OrderSide.BUY)

    if self._is_halted(asset):
        raise TradingHaltedError(asset)

    est_price = price
    if est_price == 0:
        _, up_limit = self._get_price_limits(asset)
        est_price = up_limit
        # 如果 up_limit 为 0 (无涨跌停限制，如新股)，则使用 lastPrice 估算
        if est_price <= 0:
            quote = self._get_quote(asset)
            if quote:
                est_price = quote.get("lastPrice", 0)
    return est_price


def _validated_sell_order(
    self: PaperOrders,
    asset: str,
    shares: float,
    price: float,
    order_time: datetime.datetime | None,
) -> Order:
    """Validate sell availability and market constraints before creating an order."""
    if asset not in self._positions:
        raise InsufficientPosition(security=asset, amount=shares)
    pos = self._positions[asset]
    self._validate_sell_shares(pos, shares)

    if price != 0:
        down_limit, up_limit = self._get_price_limits(asset)
        if up_limit > 0 and down_limit > 0:
            if price > up_limit or price < down_limit:
                raise PriceOutOfLimit(asset, price, down_limit, up_limit)
    self._reject_at_limit(asset, OrderSide.SELL)

    # 2. 创建订单
    order = Order(
        portfolio_id=self.portfolio_id,
        asset=asset,
        price=price,
        shares=shares,
        side=OrderSide.SELL,
        bid_type=BidType.MARKET if price == 0 else BidType.FIXED,
        tm=order_time or self._now(),
        qtoid=client_order_id.get() or new_uuid_id(),
    )
    return order


class PaperOrders:
    """Paper order entry, sizing, cancellation and session settlement."""

    if TYPE_CHECKING:
        _lock: RLock
        _cash: float
        _dry_run: bool
        _dry_run_signals: list[dict[str, Any]]
        _positions: dict[str, Position]
        _active_orders: dict[str, list[Order]]
        _order_trades: dict[str, list[Trade]]

        @property
        def portfolio_id(self) -> str: ...
        @property
        def total_assets(self) -> float: ...
        @property
        def positions(self) -> list[Position]: ...
        def _settle_previous_sessions(self) -> None: ...
        def _existing_order_result(self) -> ExecutionResult | None: ...
        def _now(self) -> datetime.datetime: ...
        def _get_today(self) -> datetime.date: ...
        def _floor_lot_size(self, shares: float) -> int: ...
        def _calculate_fee(self, amount: float, side: OrderSide) -> float: ...
        def _get_quote(self, asset: str) -> dict[str, Any] | None: ...
        def _get_price_limits(self, asset: str) -> tuple[float, float]: ...
        def _reject_at_limit(self, asset: str, side: OrderSide) -> None: ...
        def _is_halted(self, asset: str) -> bool: ...
        def _validate_sell_shares(self, pos: Position, shares: float) -> None: ...
        def _account_snapshot(self) -> Asset: ...
        async def wait(
            self, event_id: Any, timeout: float
        ) -> tuple[ExecutionResult | None, float]: ...
        def awake(self, event_id: Any, result: Any) -> None: ...

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """买入指令。

        Args:
            asset: 资产代码
            shares: 买入数量
            price: 买入价格，0 表示市价
            order_time: 下单时间
            timeout: 超时时间（秒）

        Returns:
            成交结果. dry-run 模式下返回空 ExecutionResult, 信号记录到 _dry_run_signals.

        Raises:
            InsufficientCash: 资金不足
        """
        _validate_paper_order_options(kwargs)
        self._settle_previous_sessions()
        existing = self._existing_order_result()
        if existing is not None:
            return existing

        if self._dry_run:
            self._dry_run_signals.append(
                {
                    "side": OrderSide.BUY,
                    "asset": asset,
                    "shares": shares,
                    "price": price,
                    "tm": order_time or self._now(),
                }
            )
            return ExecutionResult(qt_oid="dry-run", trades=[])

        if shares % 100 != 0:
            floored = self._floor_lot_size(shares)
            if floored <= 0:
                raise NonMultipleOfLotSize(asset, shares)
            shares = floored

        est_price = _validate_buy_reference_price(self, price, asset)

        if est_price > 0:
            est_amount = est_price * shares
            est_cost = est_amount + self._calculate_fee(est_amount, OrderSide.BUY)
            if est_cost > self._cash:
                raise InsufficientCash(asset, est_cost, self._cash)

        # 2. 创建订单
        order = Order(
            portfolio_id=self.portfolio_id,
            asset=asset,
            price=price,
            shares=shares,
            side=OrderSide.BUY,
            bid_type=BidType.MARKET if price == 0 else BidType.FIXED,
            tm=order_time or self._now(),
            qtoid=client_order_id.get() or new_uuid_id(),
        )
        db.insert_order(order)

        # 3. 加入等待队列
        with self._lock:
            self._active_orders[asset].append(order)

        # 4. 等待结果
        # 使用父类 AbstractBroker 的 wait 方法，它会返回 (result, cost_time)
        res, _ = await self.wait(order.qtoid, timeout)

        if res is None:
            # 超时，返回已有的部分成交记录（如果有）
            partial_trades = self._order_trades.get(order.qtoid, [])
            return ExecutionResult(qt_oid=order.qtoid, trades=list(partial_trades))
        return res

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """卖出指令。

        Args:
            asset: 资产代码
            shares: 卖出数量
            price: 卖出价格，0 表示市价
            order_time: 下单时间
            timeout: 超时时间（秒）

        Returns:
            成交结果. dry-run 模式下返回空 ExecutionResult, 信号记录到 _dry_run_signals.

        Raises:
            InsufficientPosition: 持仓不足
            NonMultipleOfLotSize: 卖出数量不符合手数限制（非清仓时）
        """
        _validate_paper_order_options(kwargs)
        self._settle_previous_sessions()
        existing = self._existing_order_result()
        if existing is not None:
            return existing

        if self._dry_run:
            self._dry_run_signals.append(
                {
                    "side": OrderSide.SELL,
                    "asset": asset,
                    "shares": shares,
                    "price": price,
                    "tm": order_time or self._now(),
                }
            )
            return ExecutionResult(qt_oid="dry-run", trades=[])

        # 1. 检查持仓
        order = _validated_sell_order(self, asset, shares, price, order_time)
        db.insert_order(order)

        with self._lock:
            self._active_orders[asset].append(order)

        res, _ = await self.wait(order.qtoid, timeout)
        if res is None:
            # 超时，返回已有的部分成交记录（如果有）
            partial_trades = self._order_trades.get(order.qtoid, [])
            return ExecutionResult(qt_oid=order.qtoid, trades=list(partial_trades))
        return res

    async def buy_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按总资产比例买入。

        Args:
            asset: 资产代码
            percent: 目标比例 (0.0 - 1.0)
            price: 买入价格，0 表示市价
            order_time: 下单时间
            timeout: 超时时间（秒）

        Returns:
            成交结果
        """
        _validate_paper_order_options(kwargs)
        # 计算数量
        quote = self._get_quote(asset) or {}
        if not quote:
            return ExecutionResult.empty()

        if price > 0:
            p = price
        else:
            _, up_limit = self._get_price_limits(asset)
            p = up_limit or quote.get("lastPrice", 0)
        if p <= 0:
            return ExecutionResult.empty()

        # 使用总资产计算
        target_value = self.total_assets * percent

        shares = int(target_value / p / 100) * 100
        if shares == 0:
            return ExecutionResult.empty()

        return await self.buy(asset, shares, price, order_time, timeout, **kwargs)

    async def buy_amount(
        self,
        asset: str,
        amount: int | float,
        price: int | float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按金额买入。

        Args:
            asset: 资产代码
            amount: 买入金额
            price: 买入价格，0 表示市价
            order_time: 下单时间
            timeout: 超时时间（秒）

        Returns:
            成交结果
        """
        _validate_paper_order_options(kwargs)
        quote = self._get_quote(asset) or {}
        if not quote and price == 0:
            return ExecutionResult.empty()

        if price > 0:
            p = price
        else:
            _, up_limit = self._get_price_limits(asset)
            p = up_limit or quote.get("lastPrice", 0)
        if p <= 0:
            return ExecutionResult.empty()

        shares = int(amount / p / 100) * 100
        if shares == 0:
            return ExecutionResult.empty()

        return await self.buy(asset, shares, price, order_time, timeout, **kwargs)

    async def sell_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按持仓比例卖出。

        Args:
            asset: 资产代码
            percent: 卖出比例 (0.0 - 1.0)。如果 >= 0.9999 则视为清仓。
            price: 卖出价格，0 表示市价
            order_time: 下单时间
            timeout: 超时时间（秒）

        Returns:
            成交结果
        """
        _validate_paper_order_options(kwargs)
        if asset not in self._positions:
            return ExecutionResult.empty()

        pos = self._positions[asset]
        # 如果是 1.0 (100%)，则是清仓
        if percent >= 0.9999:
            shares = pos.shares
        else:
            shares = int(pos.shares * percent / 100) * 100

        if shares == 0:
            return ExecutionResult.empty()

        return await self.sell(asset, shares, price, order_time, timeout, **kwargs)

    async def sell_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按金额卖出。

        Args:
            asset: 资产代码
            amount: 卖出金额
            price: 卖出价格，0 表示市价
            order_time: 下单时间
            timeout: 超时时间（秒）

        Returns:
            成交结果
        """
        _validate_paper_order_options(kwargs)
        quote = self._get_quote(asset) or {}
        if not quote and price == 0:
            return ExecutionResult.empty()

        if price > 0:
            p = price
        else:
            down_limit, _ = self._get_price_limits(asset)
            p = down_limit or quote.get("lastPrice", 0)
        if p <= 0:
            return ExecutionResult.empty()

        shares = int(amount / p / 100) * 100
        if shares == 0:
            # 如果金额不足1手，是否尝试卖出1手？通常不。
            # 但是如果 amount 很大导致 shares > pos.shares，sell 方法会检查并抛出异常
            return ExecutionResult.empty()

        return await self.sell(asset, shares, price, order_time, timeout, **kwargs)

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """调整持仓至目标比例。

        如果当前比例低于目标，则买入；如果高于目标，则卖出。

        Args:
            asset: 资产代码
            target_pct: 目标持仓占总资产的比例 (0.0 - 1.0)
            price: 交易价格，0 表示市价
            order_time: 下单时间
            timeout: 超时时间（秒）

        Returns:
            成交结果
        """
        _validate_paper_order_options(kwargs)
        quote = self._get_quote(asset) or {}
        if not quote and price == 0:
            return ExecutionResult.empty()

        # 计算当前价值和目标价值应该统一使用参考价格（通常是 lastPrice）
        # 只有在计算买入/卖出数量时，为了保守起见，才可能使用 limit price
        ref_price = price
        if ref_price == 0:
            ref_price = quote.get("lastPrice", 0)
            if ref_price <= 0:
                # Fallback to limit price if lastPrice is invalid
                down_limit, up_limit = self._get_price_limits(asset)
                # 如果没有 lastPrice，尝试使用涨停价作为参考
                ref_price = up_limit if up_limit > 0 else 0

        if ref_price <= 0:
            return ExecutionResult.empty()

        total = self.total_assets
        target_val = total * target_pct

        current_val = 0.0
        if asset in self._positions:
            current_val = self._positions[asset].shares * ref_price

        diff = target_val - current_val

        if diff > 0:
            # 买入
            return await self.buy_amount(asset, diff, price, order_time, timeout)
        if diff < 0:
            # 卖出
            # 注意：sell_amount 会向下取整 100 股。
            # 如果 diff 很小，可能不交易。
            # 如果希望精确清仓，可能需要特殊处理 sell_percent(0) 的情况?
            # trade_target_pct(0) -> sell all.
            if target_pct < 0.0001:
                return await self.sell_percent(
                    asset, 1.0, price=price, order_time=order_time, timeout=timeout
                )
            return await self.sell_amount(asset, -diff, price, order_time, timeout)
        return ExecutionResult.empty()

    async def cancel_order(self, qt_oid: str) -> None:
        """Persist cancellation before removing an active order or acknowledging the request."""
        with self._lock:
            found = next(
                (
                    (asset, order)
                    for asset, orders in self._active_orders.items()
                    for order in orders
                    if order.qtoid == qt_oid
                ),
                None,
            )
            if found is not None:
                asset, order = found
                self._persist_cancellation(order)
                self._active_orders[asset].remove(order)
                if not self._active_orders[asset]:
                    del self._active_orders[asset]
                trades = self._order_trades.pop(qt_oid, [])
                self.awake(qt_oid, ExecutionResult(qt_oid=qt_oid, trades=trades))
                return
            stored = db.get_order(qt_oid)
            if stored is None or stored.portfolio_id != self.portfolio_id:
                return
            if stored.status in {
                OrderStatus.UNREPORTED,
                OrderStatus.WAIT_REPORTING,
                OrderStatus.REPORTED,
                OrderStatus.PART_SUCC,
            }:
                self._persist_cancellation(stored)

    def _persist_cancellation(self, order: Order) -> None:
        status = OrderStatus.PARTSUCC_CANCEL if order.filled > 0 else OrderStatus.CANCELED
        db.update_order(
            order.qtoid, status=status.value, status_msg="Canceled by user", filled=order.filled
        )
        order.status = status
        order.status_msg = "Canceled by user"

    async def cancel_all_orders(self, side: OrderSide | None = None) -> None:
        """Cancel a snapshot of the active queue through the same durable acknowledgement path."""
        with self._lock:
            identities = [
                order.qtoid
                for orders in self._active_orders.values()
                for order in orders
                if side is None or order.side == side
            ]
        for identity in identities:
            await self.cancel_order(identity)

    async def on_day_open(self, limits: dict[str, dict[str, float]] | None = None) -> None:
        """开盘处理。

        Args:
            limits: 涨跌停限制 {asset: {'up': float, 'down': float}}
        """
        # 仿真 broker 实时从 quote 获取 limit，此处暂不需要特殊处理
        pass

    async def on_day_close(self, close_prices: dict[str, float] | None = None) -> None:
        """收盘后处理：生成资产快照，并清理未完成订单。

        Args:
            close_prices: 收盘价 {asset: price}
        """
        # 1. 撤销所有未完成订单
        # 盘后自动撤单
        await self.cancel_all_orders()

        # 清理可能残留的 early results
        if hasattr(self, "_early_results"):
            self._early_results.clear()

        with self._lock:
            today = self._get_today()

            # Sync positions with latest prices

            for asset, pos in self._positions.items():
                pos.dt = today

                price = 0.0
                if close_prices and asset in close_prices:
                    price = close_prices[asset]
                else:
                    # Try live quote or fallback to cost
                    quote = self._get_quote(asset)
                    price = quote.get("lastPrice", 0) if quote else 0
                    if price <= 0:
                        price = pos.price

                pos.mv = pos.shares * price
                pos.profit = (price - pos.price) * pos.shares

                # T+1 结算：收盘后，所有持仓在下一交易日均可用
                pos.avail = pos.shares

            db.save_portfolio_snapshot(self._account_snapshot(), self.positions)
