"""Paper quote matching and atomic execution persistence."""

import datetime
import time
from _thread import RLock
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from loguru import logger

from quantide.core.enums import (
    BidType,
    OrderSide,
    OrderStatus,
)
from quantide.core.ports.broker import ExecutionResult
from quantide.data.models import Asset, Order, Position, Trade
from quantide.data.sqlite import db


class PaperMatching:
    """Paper quote matching and atomic execution persistence."""

    if TYPE_CHECKING:
        _lock: RLock
        _closed: bool
        _cash: float
        _principal: float
        _commission: float
        _min_commission: float
        _transfer_fee: float
        _stamp_tax: float
        _slippage: float
        _last_mv_update_time: float
        _market_value_update_interval: float
        _order_trades: dict[str, list[Trade]]
        _positions: dict[str, Position]
        _active_orders: dict[str, list[Order]]

        @property
        def positions(self) -> list[Position]: ...
        @property
        def portfolio_id(self) -> str: ...
        def _get_today(self) -> datetime.date: ...
        def _now(self) -> datetime.datetime: ...
        def _settle_previous_sessions(self) -> None: ...
        def _on_limit_update(self, data: dict[str, Any]) -> None: ...
        def _get_price_limits(self, asset: str) -> tuple[float, float]: ...
        def _in_auction(self, price: float) -> bool: ...
        def _auction_limit_price(self, price: float) -> float: ...
        def awake(self, event_id: Any, result: Any) -> None: ...

    def on_quote(self, data: dict[str, Any]) -> None:
        """Consume a market snapshot through the public replay boundary."""
        self._on_quote_update(data)

    def on_limit(self, data: dict[str, Any]) -> None:
        """Consume daily limits through the public replay boundary."""
        self._on_limit_update(data)

    def _on_quote_update(self, data: dict[str, Any]) -> None:
        """行情更新回调，执行撮合逻辑。

        本方法将在 MessageHub 线程中运行。更新持仓市值，并尝试撮合待处理订单。
        兼容发布者的 ``price`` 与网关的 ``lastPrice`` 两种键名。
        """
        data = self._normalize_quotes(data)
        try:
            with self._lock:
                if self._closed:
                    return
                self._settle_previous_sessions()
                self._update_positions_market_value(data)

                if not self._active_orders:
                    return

                traded_assets: set[str] = set()
                # 遍历所有待处理订单的资产
                # 使用 list() 复制 keys，因为可能会在迭代中修改字典
                for asset in list(self._active_orders.keys()):
                    if asset in data:
                        self._match_orders_for_asset(asset, data[asset], traded_assets)

                if traded_assets:
                    self._persist_updates(traded_assets)
        except Exception as e:
            logger.exception(e)

    @staticmethod
    def _normalize_quotes(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """把不同来源的快照统一成 ``lastPrice`` 键。"""
        if not data:
            return {}
        normalized: dict[str, dict[str, Any]] = {}
        for asset, raw in data.items():
            if not isinstance(raw, dict):
                continue
            price = raw.get("lastPrice")
            if price is None:
                price = raw.get("price")
            if price is None:
                continue
            try:
                value = float(price)
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            item = dict(raw)
            item["lastPrice"] = value
            normalized[str(asset)] = item
        return normalized

    def _update_positions_market_value(self, data: dict[str, dict[str, Any]]) -> None:
        """更新内存中的持仓市值 (仅用于内存计算，不触发写库)。

        # todo: 如果存在性能问题，也许可以通过 polars 向量化操作来优化？这可能取决于有多少个资产
        """
        current_time = time.time()
        if current_time - self._last_mv_update_time < self._market_value_update_interval:
            return

        self._last_mv_update_time = current_time

        for asset, pos in self._positions.items():
            quote = data.get(asset)
            if quote:
                last_price = quote.get("lastPrice", 0)
                if last_price > 0:
                    pos.mv = pos.shares * last_price
                    pos.profit = pos.mv - (pos.shares * pos.price)

    def _match_orders_for_asset(
        self, asset: str, quote: dict[str, Any], traded_assets: set[str]
    ) -> None:
        """撮合指定资产的订单。"""
        orders = self._active_orders[asset]
        # 初始化剩余成交量
        # 如果 quote 中没有 volume 字段，则假设成交量无限大
        remaining_shares = float("inf")
        if "volume" in quote:
            remaining_shares = quote["volume"] * 100

        remaining_orders = []
        for order in orders:
            if remaining_shares <= 0:
                remaining_orders.append(order)
                continue

            matched_shares, trade = self._try_match(
                order, quote, available_shares_limit=remaining_shares
            )

            if matched_shares > 0 and trade:
                remaining_shares -= matched_shares
                self._handle_trade_execution(order, trade, asset, quote, traded_assets)

                if order.filled >= order.shares:
                    self._handle_order_completion(order)
                else:
                    self._handle_order_partial(order)
                    remaining_orders.append(order)
            else:
                remaining_orders.append(order)

        if not remaining_orders:
            del self._active_orders[asset]
        else:
            self._active_orders[asset] = remaining_orders

    def _handle_trade_execution(
        self, order: Order, trade: Trade, asset: str, quote: dict[str, Any], traded_assets: set[str]
    ) -> None:
        """处理单次成交逻辑。"""
        before = (self._cash, deepcopy(self._positions), order.filled, order.status)
        try:
            order.filled += trade.shares
            order.status = (
                OrderStatus.SUCCEEDED if order.filled >= order.shares else OrderStatus.PART_SUCC
            )
            self._apply_trade_to_portfolio(trade)
            pos = self._positions.get(asset)
            if pos:
                pos.mv = pos.shares * quote["lastPrice"]
                pos.profit = pos.mv - pos.shares * pos.price
            snapshot = self._account_snapshot()
            db.save_paper_execution(order, trade, snapshot, self.positions)
        except BaseException:
            self._cash, self._positions, order.filled, order.status = before
            raise
        self._order_trades[order.qtoid].append(trade)
        traded_assets.add(asset)

    def _handle_order_completion(self, order: Order) -> None:
        """处理订单完全成交。"""
        order.status = OrderStatus.SUCCEEDED
        # 更新 Order 状态到 DB
        db.update_order(order.qtoid, status=order.status.value, filled=order.filled)

        # 唤醒等待的协程，返回所有成交记录
        all_trades = self._order_trades.pop(order.qtoid)
        self.awake(order.qtoid, ExecutionResult(qt_oid=order.qtoid, trades=all_trades))

    def _handle_order_partial(self, order: Order) -> None:
        """处理订单部分成交。"""
        order.status = OrderStatus.PART_SUCC
        # 更新 Order 状态到 DB
        db.update_order(order.qtoid, status=order.status.value, filled=order.filled)

    def _persist_updates(self, traded_assets: set[str]) -> None:
        """持久化持仓和资产信息。"""
        db.save_portfolio_snapshot(self._account_snapshot(), self.positions)

    def _account_snapshot(self) -> Asset:
        today = self._get_today()
        for position in self._positions.values():
            position.dt = today
        market_value = sum(position.mv for position in self._positions.values())
        return Asset(
            portfolio_id=self.portfolio_id,
            dt=today,
            principal=self._principal,
            cash=self._cash,
            frozen_cash=0,
            market_value=market_value,
            total=self._cash + market_value,
        )

    def _try_match(
        self, order: Order, quote: dict[str, Any], available_shares_limit: float = float("inf")
    ) -> tuple[float, Trade | None]:
        """Check price eligibility, then create one fill bounded by the available quote volume."""
        last_price = quote.get("lastPrice", 0)
        order_time = order.tm
        if isinstance(order_time, datetime.datetime) and order_time.date() > self._now().date():
            return 0.0, None
        if last_price <= 0 or not self._order_price_eligible(order, last_price):
            return 0.0, None
        if not self._auction_order_eligible(order, last_price):
            return 0.0, None
        direction = 1 if order.side == OrderSide.BUY else -1
        match_price = (
            round(last_price * (1.0 + self._slippage * direction), 4)
            if self._slippage > 0
            else last_price
        )
        matched = min(order.shares - order.filled, available_shares_limit)
        if matched <= 0:
            return 0.0, None
        trade = Trade(
            portfolio_id=self.portfolio_id,
            tid=f"t_{order.qtoid}_{int(order.filled + matched)}",
            qtoid=order.qtoid,
            foid="",
            asset=order.asset,
            shares=matched,
            price=match_price,
            amount=match_price * matched,
            tm=order.tm or self._now(),
            side=order.side,
            cid="",
            fee=self._calculate_fee(match_price * matched, order.side),
        )
        return matched, trade

    def _order_price_eligible(self, order: Order, price: float) -> bool:
        down, up = self._get_price_limits(order.asset)
        if order.side == OrderSide.BUY and up > 0 and price >= up:
            return False
        if order.side == OrderSide.SELL and down > 0 and price <= down:
            return False
        if order.bid_type != BidType.FIXED:
            return True
        return (order.side == OrderSide.BUY and order.price >= price) or (
            order.side == OrderSide.SELL and order.price <= price
        )

    def _auction_order_eligible(self, order: Order, price: float) -> bool:
        if not self._in_auction(price) or order.side != OrderSide.BUY or order.price <= 0:
            return True
        _, up = self._get_price_limits(order.asset)
        at_up_limit = up > 0 and price >= up - 1e-9
        return at_up_limit or order.price >= self._auction_limit_price(price) - 1e-9

    def _calculate_fee(self, amount: float, side: OrderSide) -> float:
        """计算手续费 (FR-180).

        Args:
            amount: 成交金额
            side: 订单方向

        Returns:
            fee = 佣金 (max(5.0, amount * commission)) + 印花税 (仅卖方, amount * stamp_tax)
        """
        commission = max(self._min_commission, amount * self._commission)
        transfer = amount * self._transfer_fee
        stamp = amount * self._stamp_tax if side == OrderSide.SELL else 0.0
        return commission + transfer + stamp

    def _apply_trade_to_portfolio(self, trade: Trade) -> None:
        """应用成交到投资组合（仅更新内存状态）。

        更新现金、持仓数量、持仓成本。
        注意：不更新市值（MV）和盈亏，也不负责数据库同步。

        Args:
            trade: 成交记录
        """
        today = self._get_today()

        if trade.side == OrderSide.BUY:
            self._cash -= trade.amount + trade.fee
            if trade.asset in self._positions:
                pos = self._positions[trade.asset]
                # 更新成本价（含买入手续费）
                new_shares = pos.shares + trade.shares
                if new_shares > 0:
                    total_cost = pos.shares * pos.price + trade.amount + trade.fee
                    pos.price = total_cost / new_shares
                pos.shares = new_shares
                # T+1: avail 不变
            else:
                # 新建持仓（成本价含买入手续费）
                pos = Position(
                    portfolio_id=self.portfolio_id,
                    dt=today,
                    asset=trade.asset,
                    shares=trade.shares,
                    price=(trade.amount + trade.fee) / trade.shares,
                    avail=0,  # T+1
                    mv=trade.amount,  # 此时成交额即为市值
                    profit=0.0,
                )
                self._positions[trade.asset] = pos
        else:
            self._cash += trade.amount - trade.fee
            if trade.asset in self._positions:
                pos = self._positions[trade.asset]
                pos.shares -= trade.shares
                pos.avail -= trade.shares  # Reduce avail immediately

                if pos.shares <= 0:
                    del self._positions[trade.asset]
