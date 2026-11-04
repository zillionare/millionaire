"""Backtest execution commands and account queries."""

from __future__ import annotations

import datetime
import math
import uuid
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import polars as pl

from quantide.core.enums import BidType, FrameType, OrderSide, OrderStatus
from quantide.core.errors import (
    BadPercent,
    InsufficientCash,
    InsufficientPosition,
    LimitPrice,
    NoDataForMatch,
    NonMultipleOfLotSize,
    PriceNotMeet,
    TradeError,
    TradingHaltedError,
)
from quantide.core.ports.broker import ExecutionResult
from quantide.data.models import Order, Position, Trade
from quantide.data.sqlite import db

if TYPE_CHECKING:
    from quantide.service.bar_views import HistBarView
    from quantide.service.datafeed import BarsFeedImpl


def _prepare_backtest_buy_order(
    self: BacktestOrders,
    bars: pl.DataFrame | None,
    asset: str,
    order_time: datetime.datetime,
    kwargs: dict[str, Any],
    price: float,
    shares: int | float,
) -> Order:
    """Prepare backtest buy order."""
    if bars is None or bars.is_empty():
        self._log(
            "WARNING",
            f"failed to match {asset}, no data at {order_time}",
            dt=order_time,
        )
        raise NoDataForMatch(asset, order_time)

    # 3. 根据报单价格（考虑涨停）和 shares 确定现金是否充足
    # 日线取第一行，分钟线也取第一行作为报单时的参考价
    row = bars.row(0, named=True)
    up_limit = row.get("up_limit", 0.0)

    # 处理 extra 信息
    extra = kwargs.get("extra", {})
    import json

    extra_json = json.dumps(extra) if extra else ""

    # 集合竞价：市价买以「竞价价×(1+eps)」为限价，成交价仍为竞价价。
    bid_price = price
    if bid_price == 0 and self.is_auction_time(order_time):
        bid_price = self._auction_bid_price(bars, OrderSide.BUY) or up_limit
    if bid_price == 0:
        bid_price = up_limit

    # 4. 创建 Order 记录（忠实记录用户请求的份额）
    order = Order(
        portfolio_id=self._portfolio_id,
        asset=asset,
        price=bid_price,
        shares=shares,
        side=OrderSide.BUY,
        bid_type=BidType.MARKET if price == 0 else BidType.FIXED,
        tm=order_time,
        extra=extra_json,
    )
    return order


def _prepare_risk_exit_order(
    self: BacktestOrders,
    order_time: datetime.datetime,
    asset: str,
    shares: int | float,
    price: float,
    reason: str,
) -> tuple[float, Order]:
    """Prepare risk exit order."""
    self.set_clock(order_time)
    pos = self._positions.get(asset)
    if pos is None:
        raise InsufficientPosition(asset, shares)
    self._validate_sell_shares(pos, shares)

    bars = self._price_for_match(asset, order_time)
    if bars is None or bars.is_empty():
        raise NoDataForMatch(asset, order_time)
    row = bars.row(0, named=True)
    close = float(row["close"])
    down_limit = float(row.get("down_limit", 0.0) or 0.0)
    volume = float(row.get("volume", 0.0) or 0.0)
    if volume <= 0:
        raise TradingHaltedError(asset)
    if down_limit <= 0:
        self._log(
            "WARNING",
            f"资产 {asset} 缺少跌停价数据，拒绝成交",
            dt=order_time,
        )
        raise LimitPrice(asset, price)
    if price <= down_limit:
        raise LimitPrice(asset, price)

    import json

    order = Order(
        portfolio_id=self._portfolio_id,
        asset=asset,
        price=float(price),
        shares=shares,
        side=OrderSide.SELL,
        bid_type=BidType.FIXED,
        tm=order_time,
        extra=json.dumps({"reason": reason}) if reason else "",
    )
    return close, order


def _prepare_backtest_sell_order(
    self: BacktestOrders,
    bars: pl.DataFrame | None,
    asset: str,
    order_time: datetime.datetime,
    price: float,
    shares: int | float,
    kwargs: dict[str, Any],
) -> Order:
    """Prepare backtest sell order."""
    if bars is None or bars.is_empty():
        self._log(
            "WARNING",
            f"failed to match {asset}, no data at {order_time}",
            dt=order_time,
        )
        raise NoDataForMatch(asset, order_time)

    # 2. 确定基准价格
    row = bars.row(0, named=True)
    down_limit = row.get("down_limit", 0.0)
    ask_price = price
    if ask_price == 0 and self.is_auction_time(order_time):
        ask_price = self._auction_bid_price(bars, OrderSide.SELL) or down_limit
    if ask_price == 0:
        ask_price = down_limit

    if ask_price == 0:
        self._log(
            "WARNING",
            f"failed to match {asset}, no valid price at {order_time}",
            dt=order_time,
        )
        raise NoDataForMatch(asset, order_time)

    # 3. 严格校验：份额必须是 100 的整数倍（除非清仓）且有可用持仓
    pos = self._positions.get(asset)
    if pos is None:
        raise InsufficientPosition(asset, shares)

    self._validate_sell_shares(pos, shares)

    # 处理 extra 信息
    extra = kwargs.get("extra", {})
    import json

    extra_json = json.dumps(extra) if extra else ""

    # 4. 创建 Order 记录
    order = Order(
        portfolio_id=self._portfolio_id,
        asset=asset,
        price=ask_price,
        shares=shares,
        side=OrderSide.SELL,
        bid_type=BidType.MARKET if price == 0 else BidType.FIXED,
        tm=order_time,
        extra=extra_json,
    )
    return order


class BacktestOrders:
    """Backtest execution commands and account queries."""

    if TYPE_CHECKING:
        _portfolio_id: str
        _portfolio_name: str
        _cash: float
        _principal: float
        _commission: float
        _stamp_duty: float
        _min_commission: float
        _transfer_fee: float
        _positions: dict[str, Position]
        _data_feed: BarsFeedImpl
        _bar_view: HistBarView
        _match_level: Literal["day", "minute"]
        _risk_overlay_in_progress: bool
        _risk_overlay_sold_assets: set[str]
        allow_same_bar_repurchase: bool

        def as_date(self, dt: datetime.date | datetime.datetime) -> datetime.date: ...
        def set_clock(self, dt: datetime.datetime) -> None: ...
        def _validate_sell_shares(self, pos: Position, shares: float) -> None: ...
        def is_auction_time(self, tm: datetime.datetime) -> bool: ...
        def _auction_bid_price(self, bars: pl.DataFrame, side: OrderSide) -> float: ...
        def _price_for_match(
            self, asset: str, tm: datetime.datetime, fill_timing: str = ""
        ) -> pl.DataFrame | None: ...
        def _log(
            self,
            level: str,
            message: str,
            dt: datetime.date | datetime.datetime | None = None,
            extra: dict[str, Any] | None = None,
        ) -> None: ...

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        # 在回测中，timeout 参数无效，直接忽略
        _ = timeout

        if not self.allow_same_bar_repurchase and asset in self._risk_overlay_sold_assets:
            self._log(
                "INFO",
                f"risk overlay blocked same-bar repurchase for {asset}",
                dt=order_time,
            )
            return ExecutionResult.empty()

        assert order_time is not None, "order_time must be present in backtest mode"
        self.set_clock(order_time)

        # 1. 份额必须是 100 的整数倍
        if int(shares) % 100 != 0:
            raise NonMultipleOfLotSize(asset, shares)

        # 2. 获取撮合所需的行情数据
        bars = self._price_for_match(asset, order_time, str(kwargs.get("fill_timing", "")).lower())
        order = _prepare_backtest_buy_order(self, bars, asset, order_time, kwargs, price, shares)
        assert bars is not None  # The preparation helper rejects missing bars.
        db.insert_order(order)

        # 5. 执行撮合
        try:
            if self._match_level == "minute":
                trade = self._match_bid_minute(order, bars)
            else:
                trade = self._match_bid_day(order, bars)

            return ExecutionResult(qt_oid=order.qtoid, trades=[trade])
        except TradeError as e:
            # 在废单的情况下，保留已插入的订单记录并更新状态，
            # 避免重复插入同一个 qtoid 触发唯一约束异常。
            order.status = OrderStatus.JUNK
            order.status_msg = str(e)
            db.update_order(
                order.qtoid,
                status=order.status.value,
                status_msg=order.status_msg,
                filled=order.filled,
                error=str(e),
            )
            raise e

    def _match_bid_day(self, order: Order, bars: pl.DataFrame) -> Trade:
        """日线撮合逻辑：不考虑成交量，直接全额成交

        Args:
            order: 订单
            bars: 日线行情数据

        Raises:
            InsufficientCash: 资金不足

        """
        row = bars.row(0, named=True)

        up_limit = row.get("up_limit", 0.0)
        bid_price = order.price

        # 用以计算当天的市值
        close = row["close"]

        market_open = datetime.time(9, 30)
        match_price = row["open"] if order.tm.time() <= market_open else row["close"]

        # 缺少涨停价数据：无法判断能否成交，保守拒绝并告警
        if up_limit <= 0:
            self._log(
                "WARNING",
                f"资产 {order.asset} 在 {row['date']} 缺少涨停价数据，拒绝成交",
                dt=order.tm,
            )
            raise LimitPrice(order.asset, match_price)

        # 成交时间点已涨停，不允许成交
        if match_price >= up_limit:
            self._log(
                "WARNING",
                f"资产 {order.asset} 在 {row['date']} 处于涨停，无法成交",
                dt=order.tm,
            )
            raise LimitPrice(order.asset, match_price)

        if bid_price > 0 and bid_price < match_price:
            self._log(
                "WARNING",
                f"资产 {order.asset} 委托价 {bid_price} 低于撮合价 {match_price}，无法成交",
                dt=order.tm,
            )
            raise PriceNotMeet(order.asset, bid_price, match_price)

        estimated_amount = order.shares * bid_price
        required_cash = estimated_amount + self._calc_fee(estimated_amount, OrderSide.BUY)
        if required_cash > self._cash:
            self._log(
                "INFO",
                (
                    "委买失败："
                    f"{order.asset}"
                    ", 资金("
                    f"{self._cash:.2f}"
                    ")不足以按价格 "
                    f"{bid_price:.2f}"
                    " 购买 "
                    f"{order.shares}"
                    " 股。"
                ),
                dt=order.tm,
            )
            raise InsufficientCash(self._portfolio_name, required_cash, self._cash)

        return self._execute_trade(order, match_price, close=close)

    def _match_bid_minute(self, order: Order, bars: pl.DataFrame) -> Trade:
        """分钟线撮合逻辑：按成交量匹配，并计算出成交均价

        Args:
            order: 订单
            bars: 分钟线行情数据

        Returns:
            成交数量、均价和完成时间
        """
        # feed 保证返回的 bars 一定有数据，否则返回 None
        row = bars.row(0, named=True)
        up_limit = row.get("up_limit", 0.0)
        if up_limit <= 0:
            self._log(
                "WARNING",
                f"资产 {order.asset} 缺少涨停价数据，拒绝成交",
                dt=order.tm,
            )
            raise LimitPrice(order.asset, float(row.get("close", 0.0) or 0.0))

        # 提取当天收盘价，计算市值时使用
        close = bars.row(-1, named=True)["close"]

        bars = self._remove_for_bid(bars, order.price, up_limit)

        if bars.is_empty():
            raise NoDataForMatch(order.asset, order.tm)

        mean_price, filled, tm = self._match_shares(bars, order.shares)

        if filled == 0:
            raise NoDataForMatch(order.asset, order.tm)

        return self._execute_trade(
            order,
            mean_price,
            close=close,
            tm=tm,
            shares=filled,
        )

    async def execute_exit(
        self,
        asset: str,
        shares: int | float,
        price: float,
        order_time: datetime.datetime,
        reason: str = "",
    ) -> ExecutionResult:
        """Execute a risk exit at an explicit simulated intraday price.

        Used by registered overlays for same-bar explicit-price exits. The fill
        is still constrained by A-share price limits and suspension.
        """
        close, order = _prepare_risk_exit_order(self, order_time, asset, shares, price, reason)
        db.insert_order(order)
        try:
            trade = self._execute_trade(
                order,
                float(price),
                close=close,
                tm=order_time,
                shares=shares,
            )
            if self._risk_overlay_in_progress:
                self._risk_overlay_sold_assets.add(asset)
            return ExecutionResult(qt_oid=order.qtoid, trades=[trade])
        except TradeError as exc:
            order.status = OrderStatus.JUNK
            order.status_msg = str(exc)
            db.update_order(
                order.qtoid,
                status=order.status.value,
                status_msg=order.status_msg,
                filled=order.filled,
                error=str(exc),
            )
            raise

    def _calc_fee(self, amount: float, side: OrderSide) -> float:
        """计算单笔成交的全部费用（佣金、过户费、卖方印花税）。"""
        if amount <= 0:
            return 0.0
        commission = max(amount * self._commission, self._min_commission)
        transfer = amount * self._transfer_fee
        stamp = amount * self._stamp_duty if side == OrderSide.SELL else 0.0
        return commission + transfer + stamp

    def _execute_trade(
        self,
        order: Order,
        price: float,
        close: float,
        tm: datetime.datetime | None = None,
        shares: float | None = None,
    ) -> Trade:
        """执行成交并更新状态

        将根据 order 方法来计算 cash， 创建 Trade， 创建（更新） assets, positions 表格
        Args:
            order: 订单
            price: 成交均价
            close: 当日收盘价
            tm: 成交时间
            shares: 成交数量

        Returns:
            成交结果
        """
        shares = shares or order.shares
        tm = tm or order.tm

        # 1. 创建成交记录
        amount = shares * price

        fee = self._calc_fee(amount, order.side)

        trade = Trade(
            portfolio_id=self._portfolio_id,
            tid=uuid.uuid4().hex,
            qtoid=order.qtoid,
            foid="",
            asset=order.asset,
            shares=shares,
            price=price,
            amount=amount,
            tm=tm,
            side=order.side,
            cid="",
            fee=fee,
        )
        db.insert_trades(trade)

        # 2. 更新内存中的现金和持仓
        if order.side == OrderSide.BUY:
            self._cash -= amount + fee
            pos = self._positions.get(order.asset)
            if pos:
                total_shares = pos.shares + shares
                # Position cost basis is the all-in acquisition cost, including
                # the fee charged for this buy.
                new_price = (pos.shares * pos.price + amount + fee) / total_shares
                pos.shares = total_shares
                pos.price = new_price
                pos.profit = 0
                pos.mv = pos.shares * close  # 更新市值为当前收盘价 * 总持仓
                # avail 保持不变
            else:
                self._positions[order.asset] = Position(
                    portfolio_id=self._portfolio_id,
                    dt=self.as_date(tm),
                    asset=order.asset,
                    shares=shares,
                    price=(amount + fee) / shares,
                    avail=0,  # T+1 规则：当日买入的持仓 avail 为 0
                    mv=shares * close,
                    profit=0,
                )
        else:
            self._cash += amount - fee
            pos = self._positions.get(order.asset)
            if pos:
                pos.shares -= shares
                pos.avail -= shares
                pos.profit = 0
                pos.mv = pos.shares * close  # 更新市值为当前收盘价 * 剩余持仓
                if pos.shares <= 0:
                    del self._positions[order.asset]

        # 更新持仓记录。按完整快照写入，清仓标的不能留在当天记录中。
        db.replace_positions(self._portfolio_id, self.as_date(tm), list(self._positions.values()))

        # 更新 asset 记录
        mv = np.sum([pos.mv for pos in self._positions.values()])
        total = self._cash + mv
        # 更新资产记录
        db.update_asset(
            dt=self.as_date(tm),
            portfolio_id=self._portfolio_id,
            cash=self._cash,
            total=total,
            market_value=mv,
            principal=self._principal,
        )

        return trade

    def market_value(self) -> float:
        """获取当前总市值

        本方法使用内存中的 positions 缓存快速计算，不刷新数据，最终结果为近似值。
        """
        return float(np.sum([pos.mv for pos in self._positions.values()]))

    def total_asset(self) -> float:
        """获取当前总资产

        本方法使用内存中的 positions 缓存与 cash 快速计算，不刷新数据，最终结果为近似值。
        """
        return self._cash + self.market_value()

    async def buy_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        _ = timeout

        if not 0 < percent <= 1:
            raise BadPercent(percent)

        return await self.buy_amount(
            asset, self._cash * percent, price, order_time, timeout, **kwargs
        )

    async def buy_amount(
        self,
        asset: str,
        amount: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        _ = timeout
        assert order_time is not None, "order_time must be present in backtest mode"

        # 获取预估价格
        if price > 0:
            est_price = price
        elif self.is_auction_time(order_time):
            bars = self._price_for_match(asset, order_time)
            est_price = (
                self._auction_bid_price(bars, OrderSide.BUY)
                if bars is not None and not bars.is_empty()
                else 0.0
            )
            if est_price <= 0:
                _, up_limit = self._data_feed.get_trade_price_limits(
                    asset, self.as_date(order_time)
                )
                est_price = up_limit
        else:
            _, up_limit = self._data_feed.get_trade_price_limits(asset, self.as_date(order_time))
            est_price = up_limit

        if est_price <= 0:
            raise NoDataForMatch(asset, order_time)

        shares = amount / (est_price * (1 + self._commission + self._transfer_fee))

        shares = int(shares // 100) * 100
        if shares == 0:
            return ExecutionResult.empty()

        return await self.buy(asset, shares, price, order_time, timeout, **kwargs)

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        _ = timeout

        assert order_time is not None, "order_time must be present in backtest mode"
        self.set_clock(order_time)

        # 1. 获取撮合所需的行情数据
        bars = self._price_for_match(asset, order_time, str(kwargs.get("fill_timing", "")).lower())
        order = _prepare_backtest_sell_order(self, bars, asset, order_time, price, shares, kwargs)
        assert bars is not None  # The preparation helper rejects missing bars.
        db.insert_order(order)

        # 5. 执行撮合
        try:
            if self._match_level == "minute":
                trade = self._match_ask_minute(order, bars)
            else:
                trade = self._match_ask_day(order, bars)

            if self._risk_overlay_in_progress:
                self._risk_overlay_sold_assets.add(asset)
            return ExecutionResult(qt_oid=order.qtoid, trades=[trade])
        except TradeError as e:
            # 在废单的情况下，保留已插入的订单记录并更新状态。
            order.status = OrderStatus.JUNK
            order.status_msg = str(e)
            db.update_order(
                order.qtoid,
                status=order.status.value,
                status_msg=order.status_msg,
                filled=order.filled,
                error=str(e),
            )
            raise e

    def _match_ask_day(self, order: Order, bars: pl.DataFrame) -> Trade:
        """日线卖出撮合逻辑"""
        row = bars.row(0, named=True)

        down_limit = row.get("down_limit", 0.0)
        ask_price = order.price or down_limit

        # 用以计算当天的市值
        close = row["close"]

        market_open = datetime.time(9, 30)
        match_price = row["open"] if order.tm.time() <= market_open else row["close"]

        if down_limit <= 0:
            self._log(
                "WARNING",
                f"资产 {order.asset} 在 {row['date']} 缺少跌停价数据，拒绝成交",
                dt=order.tm,
            )
            raise LimitPrice(order.asset, match_price)

        if match_price <= down_limit:
            self._log(
                "WARNING",
                f"资产 {order.asset} 在 {row['date']} 处于跌停，无法成交",
                dt=order.tm,
            )
            raise LimitPrice(order.asset, match_price)

        if ask_price > 0 and ask_price > match_price:
            self._log(
                "WARNING",
                f"资产 {order.asset} 委托价 {ask_price} 高于撮合价 {match_price}，无法成交",
                dt=order.tm,
            )
            raise PriceNotMeet(order.asset, ask_price, match_price)

        return self._execute_trade(order, match_price, close=close)

    def _match_ask_minute(self, order: Order, bars: pl.DataFrame) -> Trade:
        """分钟线撮合逻辑：按成交量匹配"""
        # feed 保证返回的 bars 一定有数据，否则返回 None
        row = bars.row(0, named=True)
        down_limit = row.get("down_limit", 0.0)
        if down_limit <= 0:
            self._log(
                "WARNING",
                f"资产 {order.asset} 缺少跌停价数据，拒绝成交",
                dt=order.tm,
            )
            raise LimitPrice(order.asset, float(row.get("close", 0.0) or 0.0))

        # 提取当天收盘价，计算市值时使用
        close = bars.row(-1, named=True)["close"]

        bars = self._remove_for_ask(bars, order.price, down_limit)
        if bars.is_empty():
            raise NoDataForMatch(order.asset, order.tm)

        mean_price, filled, tm = self._match_shares(bars, order.shares)

        if filled == 0:
            raise NoDataForMatch(order.asset, order.tm)

        return self._execute_trade(
            order,
            mean_price,
            close=close,
            tm=tm,
            shares=filled,
        )

    def _match_shares(
        self, bars: pl.DataFrame, shares: float
    ) -> tuple[float, float, datetime.datetime]:
        """对分钟线匹配成交量，返回均价，filled 及最后匹配的时间

        Args:
            bars (pl.DataFrame): 已移除掉无法匹配的分钟线的数据
            shares (float): 要匹配的股数

        Returns:
            均价，filled 及最后成交时间
        """
        # 来自 zillionare-backtesting
        c = bars["price"].to_numpy()

        # volume 是手数，转换成股数，以便与 shares 比较
        v = bars["volume"].to_numpy() * 100
        times = bars["tm"].to_list()

        cum_v = np.cumsum(v)

        # until i the order can be filled
        where_total_filled = np.argwhere(cum_v >= shares)
        if len(where_total_filled) == 0:
            i = len(v) - 1
        else:
            i = int(np.min(where_total_filled))

        # 也许到当天结束，都没有足够的股票
        filled = min(cum_v[i], shares)

        # 最后一周期，只需要成交剩余的部分
        vol = v[: i + 1].copy()
        vol[-1] = filled - np.sum(vol[:-1])

        money = sum(c[: i + 1] * vol)
        mean_price = money / filled

        return mean_price, filled, times[i]

    def _remove_for_bid(
        self, bars: pl.DataFrame, bid_price: float, up_limit: float
    ) -> pl.DataFrame:
        """分钟线买入：只要 bar 未“完全封死”在涨停，就允许成交。

        - ``low < up_limit`` 表示该 bar 内曾出现低于涨停价的价格；
        - 成交价仍使用 bar 价格（若收在涨停，即按涨停价成交）；
        - 全天/整段完全封死（``low >= up_limit``）的 bar 不参与撮合。
        """
        return bars.filter(
            (pl.col("low") < up_limit)
            & (pl.col("close") <= bid_price)
            & (pl.col("volume").is_not_null())
            & (pl.col("volume") > 0)
        )

    def _remove_for_ask(
        self, bars: pl.DataFrame, ask_price: float, down_limit: float
    ) -> pl.DataFrame:
        """分钟线卖出：只要 bar 未“完全封死”在跌停，就允许成交。

        - ``high > down_limit`` 表示该 bar 内曾出现高于跌停价的价格；
        - 成交价仍使用 bar 价格（若收在跌停，即按跌停价成交）。
        """
        return bars.filter(
            (pl.col("high") > down_limit)
            & (pl.col("close") >= ask_price)
            & (pl.col("volume").is_not_null())
            & (pl.col("volume") > 0)
        )

    async def sell_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """按持仓百分比卖出"""
        _ = timeout

        assert order_time is not None, "order_time must be present in backtest mode"
        # buy/sell会设置时钟

        if not 0 < percent <= 1:
            raise BadPercent(percent)

        pos = self._positions.get(asset)
        if pos is None:
            raise InsufficientPosition(asset, 0)

        # sell will validate shares
        shares = pos.avail * percent

        return await self.sell(asset, shares, price, order_time, timeout, **kwargs)

    async def sell_amount(
        self,
        asset: str,
        amount: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        method: Literal["ceil", "floor"] = "ceil",
        **kwargs: Any,
    ) -> ExecutionResult:
        _ = timeout

        assert order_time is not None, "order_time must be present in backtest mode"

        if price > 0:
            est_price = price
        else:
            down_limit, _ = self._data_feed.get_trade_price_limits(asset, self.as_date(order_time))
            est_price = down_limit

        # 没提供报价，又未能获得跌停价
        if est_price <= 0:
            raise NoDataForMatch(asset, order_time)

        if method == "ceil":
            shares = math.ceil(amount / est_price / 100) * 100
        else:
            shares = int(amount / est_price / 100) * 100

        if shares == 0:
            return ExecutionResult.empty()

        return await self.sell(asset, shares, est_price, order_time, timeout, **kwargs)

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """将`asset`仓位调整到占总市值的`target_pct`

        受市值波动影响，以及可能还有其它标的的仓位也要调整，
        所以最终仓位可能与目标仓位不完全一致。
        如果当前仓位非常接近目标仓位（差别不足一手），则不进行调整，
        此时返回`ExecutionResult.empty()`

        Args:
            asset: 资产代码，"symbol.SZ"风格
            target_pct: 目标仓位占比，0-1 之间的浮点数
            price: 委托价格. Defaults to 0.
            order_time: 委托时间.

        Returns:
            ExecutionResult: 交易结果
        """
        total = self.total_asset()

        target_mv = total * target_pct
        pos = self._positions.get(asset)
        if pos is None:
            return await self.buy_amount(asset, target_mv, price, order_time, timeout, **kwargs)

        margin = target_mv - pos.mv
        if margin > 0:
            return await self.buy_amount(asset, margin, price, order_time, timeout, **kwargs)
        else:
            return await self.sell_amount(
                asset, -margin, price, order_time, timeout, method="floor", **kwargs
            )

    async def cancel_order(self, qt_oid: str) -> None:
        """回测模式下，不支持取消订单"""
        return None

    async def cancel_all_orders(self, side: OrderSide | None = None) -> None:
        """回测模式下，不支持取消订单"""
        return None

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: FrameType | str = FrameType.DAY,
        skip_suspended: bool = True,
        fill_value: bool = True,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """获取回测历史行情。

        日线回测默认在开盘时生成信号，因此当 ``end_dt`` 落在开盘时刻或更早时，
        当前交易日尚未完成，历史窗口只能看到上一交易日的数据，避免前视偏差。

        Args:
            asset: 资产代码。
            count: 历史 bar 数量。
            end_dt: 截止时间，包含边界。
            frame_type: 周期类型，目前仅支持 ``1d``。
            skip_suspended: 预留参数，当前未使用。
            fill_value: 预留参数，当前未使用。
            include_forming_bar: 回测模式下不适用（无实时 tick 注入），保留参数以
                与 sim/gateway broker 接口一致。

        Returns:
            历史日线数据。
        """
        _ = skip_suspended
        _ = fill_value
        _ = include_forming_bar
        return self._bar_view.get_history(asset, count, end_dt, frame_type)

    def get_bars_range(
        self,
        assets: list[str] | None,
        start_dt: datetime.datetime | datetime.date,
        end_dt: datetime.datetime | datetime.date | None = None,
        adjust: str | None = None,
        include_forming_bar: bool = False,
    ) -> pl.DataFrame:
        """批量日期区间日线（回测：仅已完成日线）。"""
        return self._bar_view.get_bars_range(
            assets, start_dt, end_dt, adjust=adjust, include_forming_bar=include_forming_bar
        )

    def _get_close_adjust_factors(
        self,
        assets: list[str],
        start: datetime.date,
        end: datetime.date,
    ) -> pl.DataFrame:
        """读取用于展仓的收盘价与复权因子，并兼容旧测试桩接口。"""
        if hasattr(self._data_feed, "get_close_adjust_factor"):
            frame = self._data_feed.get_close_adjust_factor(assets, start, end)
        elif hasattr(self._data_feed, "get_close_factor"):
            frame = self._data_feed.get_close_factor(assets, start, end)
        else:
            frame = None

        if frame is None or frame.is_empty():
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "asset": pl.Utf8,
                    "close": pl.Float64,
                    "adjust": pl.Float64,
                }
            )

        rename_map: dict[str, str] = {}
        if "dt" in frame.columns and "date" not in frame.columns:
            rename_map["dt"] = "date"
        if "factor" in frame.columns and "adjust" not in frame.columns:
            rename_map["factor"] = "adjust"
        if rename_map:
            frame = frame.rename(rename_map)

        if "adjust" not in frame.columns:
            frame = frame.with_columns(pl.lit(1.0).alias("adjust"))

        return frame.select(["date", "asset", "close", "adjust"]).with_columns(
            [
                pl.col("date").cast(pl.Date),
                pl.col("close").cast(pl.Float64),
                pl.col("adjust").cast(pl.Float64),
            ]
        )
