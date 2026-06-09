"""qmt-gateway 交易端口适配器."""

import datetime
from typing import Any
from uuid import uuid4

import polars as pl

from quantide.core.enums import BidType, BrokerKind, OrderSide, OrderStatus
from quantide.core.ports import (
    AssetView,
    BrokerPort,
    CancelAck,
    ExecutionResult,
    OrderAck,
    OrderRequest,
    OrderView,
    PositionView,
    TradeView,
)
from quantide.core.runtime.gateway_client import GatewayClient
from quantide.data.helper import qfq_adjustment
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import Asset, Order, Position, Trade
from quantide.service.base_broker import Broker, TradeResult
from quantide.service.livequote import live_quote


class GatewayTradeStateConsistencyError(RuntimeError):
    """Raised when gateway payloads break qtoid/external-id consistency."""


def _coerce_order_side(value: str) -> OrderSide:
    """把网关归一化后的委托方向字符串转回 ``OrderSide`` 枚举.

    网关 ``_normalize_order_status`` 不会触碰 ``side``，但客户端代码
    历史上既见过 ``"buy"`` / ``"sell"``，也见过 ``"BUY"`` / ``"SELL"``，
    甚至下单回报里可能带 ``OrderSide`` 整数值。统一在这里收敛。
    """
    text = str(value or "").strip().lower()
    if text in {"buy", "b", "1"}:
        return OrderSide.BUY
    if text in {"sell", "s", "-1"}:
        return OrderSide.SELL
    return OrderSide.UNKNOWN


def _coerce_order_status(value: str) -> OrderStatus:
    """把网关 ``_normalize_order_status`` 归一化后的字符串映射回 ``OrderStatus`` 枚举.

    网关归一化结果（参考 ``qmt_gateway/apis/trade.py::`` ``_normalize_order_status``）：

    ``"unreported"`` / ``"pending"`` / ``"reported"`` / ``"canceling"`` /
    ``"partial_canceling"`` / ``"partial_cancelled"`` / ``"cancelled"`` /
    ``"partial"`` / ``"filled"`` / ``"rejected"`` / ``"unknown"``

    下游 ``TodayOrdersTable`` 的 ``status_map`` 直接用 ``OrderStatus`` 枚举查找，
    所以必须返回枚举成员本身；任何未识别的字符串都映射成 ``OrderStatus.UNKNOWN``。
    """
    text = str(value or "").strip().lower()
    mapping: dict[str, OrderStatus] = {
        "unreported": OrderStatus.UNREPORTED,
        "pending": OrderStatus.WAIT_REPORTING,
        "reported": OrderStatus.REPORTED,
        "canceling": OrderStatus.REPORTED_CANCEL,
        "partial_canceling": OrderStatus.PARTSUCC_CANCEL,
        "partial_cancelled": OrderStatus.PART_CANCEL,
        "cancelled": OrderStatus.CANCELED,
        "canceled": OrderStatus.CANCELED,
        "partial": OrderStatus.PART_SUCC,
        "filled": OrderStatus.SUCCEEDED,
        "rejected": OrderStatus.JUNK,
    }
    return mapping.get(text, OrderStatus.UNKNOWN)


class GatewayBrokerWrapper(Broker):
    """将 GatewayBrokerAdapter 包装为旧版的 Broker 接口，以便 UI 使用。"""

    def __init__(
        self,
        adapter: "GatewayBrokerAdapter",
        portfolio_id: str = "gateway",
    ):
        self._adapter = adapter
        self._portfolio_id = portfolio_id
        self._portfolio_name = "实盘网关"
        self._kind = BrokerKind.QMT
        self._clock: datetime.datetime | None = None
        self._strategy_cheat_on_close: bool = True
        self._live_execution_window: str = "auction"
        self._live_execution_slippage: float = 0.001
        self._deferred_orders: list[dict[str, Any]] = []

    def set_clock(self, dt: datetime.datetime | None) -> None:
        """设置当前策略时钟，便于 live 回放测试复用同一路径。"""
        self._clock = dt

    def set_strategy_runtime_config(
        self,
        cheat_on_close: bool = False,
        live_execution_window: str = "auction",
        live_execution_slippage: float = 0.001,
    ) -> None:
        """由 StrategyRuntime 在启动时调一次，告知 broker 当前策略的 cheat_on_close 与延迟执行参数。"""
        self._strategy_cheat_on_close = bool(cheat_on_close)
        self._live_execution_window = str(live_execution_window)
        self._live_execution_slippage = float(live_execution_slippage)

    @property
    def deferred_orders(self) -> list[dict[str, Any]]:
        return list(self._deferred_orders)
    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: str = "1d",
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """获取 live 策略所需的历史日线数据。

        Issue #20：默认 ``include_forming_bar=True``，当 ``end_dt`` 落在今日且
        LiveQuote 已收到今日 tick 时，合并今日 forming bar 在末尾；close/high/low
        反映盘中最新状态。
        """
        if frame_type != "1d":
            raise NotImplementedError("GatewayBrokerWrapper currently only supports 1d history")

        if not hasattr(daily_bars, "get_bars") and not hasattr(daily_bars, "get_history"):
            return self._empty_history_frame()
        end_date = self._resolve_history_end_date(end_dt)
        if (
            not include_forming_bar
            and end_date == self._today()
        ):
            end_date = self._previous_trade_date(end_date)
            hist = self._provider_get_bars(daily_bars, asset, count, end_date, frame_type)
        else:
            hist = self._provider_get_bars(daily_bars, asset, count, end_date, frame_type)

        forming_applied = False
        if include_forming_bar:
            hist = self._maybe_attach_forming_bar(asset, hist, end_date, end_dt, count)
            forming_applied = True

        if (
            not forming_applied
            and "adjust" in hist.columns
            and not hist.is_empty()
        ):
            hist = qfq_adjustment(hist, adj_factor_col="adjust", eager_mode=True)
        return hist

    def _provider_get_bars(
        self, provider, asset, count, end_date, frame_type
    ) -> pl.DataFrame:
        if hasattr(provider, "get_history"):
            return provider.get_history(asset, count, end_date, frame_type)
        if hasattr(provider, "get_bars"):
            return provider.get_bars(
                n=count,
                end=end_date,
                assets=[asset],
                adjust=None,
                eager_mode=True,
            )
        return self._empty_history_frame()

    def _maybe_attach_forming_bar(
        self,
        asset: str,
        hist: pl.DataFrame,
        end_date: datetime.date,
        end_dt: datetime.datetime | None,
        count: int,
    ) -> pl.DataFrame:
        """end_date==今日且 end_dt.time()>9:30 时，合并 LiveQuote 的 forming bar.

        若 LiveQuote 还没收到今日 tick（bar 为 None）— 今日的 close 还没固定，
        退回只看昨日及更早。
        """
        if end_date != self._today():
            return hist
        if isinstance(end_dt, datetime.datetime) and end_dt.time() <= datetime.time(9, 30):
            return hist
        bar = live_quote.get_daily_bar(asset)
        if bar is None:
            return self._provider_get_bars(
                self._history_provider or daily_bars,
                asset,
                count,
                self._previous_trade_date(end_date),
                "1d",
            )
        bar_dt = bar.get("dt")
        if hasattr(bar_dt, "date"):
            bar_dt = bar_dt.date()
        if bar_dt != end_date:
            return hist
        return self._concat_forming_with_history(hist, bar, count)

    @staticmethod
    def _concat_forming_with_history(
        hist: pl.DataFrame, forming: dict, count: int
    ) -> pl.DataFrame:
        """共用 _concat_with_forming 逻辑（与 sim_broker 一致）。"""
        from quantide.service.sim_broker import PaperBroker

        return PaperBroker._concat_with_forming(hist, forming, count)

    def _previous_trade_date(self, today: datetime.date) -> datetime.date:
        try:
            return calendar.day_shift(today, -1)
        except Exception:
            return today - datetime.timedelta(days=1)

    def _resolve_history_end_date(
        self,
        end_dt: datetime.datetime | None,
    ) -> datetime.date:
        end_date = end_dt.date() if isinstance(end_dt, datetime.datetime) else self._today()
        if isinstance(end_dt, datetime.datetime) and end_dt.time() <= datetime.time(9, 30):
            try:
                return calendar.day_shift(end_date, -1)
            except Exception:
                return end_date - datetime.timedelta(days=1)
        return end_date

    def _empty_history_frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            schema={
                "date": pl.Date,
                "asset": pl.Utf8,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "amount": pl.Float64,
                "adjust": pl.Float64,
                "is_st": pl.Boolean,
                "up_limit": pl.Float64,
                "down_limit": pl.Float64,
            }
        )

    def _today(self) -> datetime.date:
        if self._clock is not None:
            return self._clock.date()
        return datetime.date.today()

    @property
    def portfolio_id(self) -> str:
        return self._portfolio_id

    @property
    def portfolio_name(self) -> str:
        return self._portfolio_name

    @property
    def kind(self) -> BrokerKind:
        return self._kind

    @property
    def status(self) -> bool:
        return True

    @property
    def is_connected(self) -> bool:
        return True

    @property
    def asset(self) -> Asset:
        view = self._adapter.query_assets()
        if not view:
            return Asset(
                portfolio_id=self._portfolio_id,
                dt=self._today(),
                principal=0,
                cash=0,
                frozen_cash=0,
                market_value=0,
                total=0,
            )
        return Asset(
            portfolio_id=self._portfolio_id,
            dt=view.dt or self._today(),
            principal=view.principal,
            cash=view.cash,
            frozen_cash=view.frozen_cash,
            market_value=view.market_value,
            total=view.total,
        )

    @property
    def cash(self) -> float:
        return self.asset.cash

    @property
    def positions(self) -> dict[str, Position]:
        """返回当前持仓."""
        views = self._adapter.query_positions()
        res = {}
        for v in views:
            res[v.asset] = Position(
                portfolio_id=self._portfolio_id,
                dt=self._today(),
                asset=v.asset,
                shares=v.shares,
                avail=v.avail,
                price=v.price,
                profit=0,
                mv=v.mv,
            )
        return res

    @property
    def orders(self) -> dict[str, Order]:
        """返回当前委托.

        Issue #29 复盘：原先此属性缺失，导致 ``/trade/`` 页面里的
        ``hasattr(broker, "orders")`` 判定为 ``False``，委托表永远空。
        补齐后页面才能拿到网关的委托数据。

        网关返回的 ``OrderView.side`` / ``OrderView.status`` 是字符串
        （来自 ``_normalize_order_status`` 的归一化结果），这里要映射
        回 ``OrderSide`` / ``OrderStatus`` 枚举，否则 ``Order.__post_init__``
        在 ``isinstance(..., int)`` 检查后保留原值，导致下游的
        ``OrderStatus.PENDING`` 之类的查找全部失败。
        """
        views = self._adapter.query_orders()
        res: dict[str, Order] = {}
        for v in views:
            side = _coerce_order_side(v.side)
            status = _coerce_order_status(v.status)
            order = Order(
                portfolio_id=self._portfolio_id,
                asset=v.asset,
                side=side,
                shares=v.shares,
                bid_type=BidType.FIXED,
                tm=v.tm or self._today(),
                price=v.price,
                filled=v.filled,
                foid=v.order_id or None,
                status=status,
                error=v.error or "",
            )
            res[order.qtoid] = order
        return res

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict | None = None,
    ) -> None:
        """记录策略运行数据.

        Gateway 兼容层当前仅用于 UI 交易与查询，不持久化策略指标。
        """

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> TradeResult:
        """按股数买入."""
        return await self._submit_legacy_order(
            asset=asset,
            side=OrderSide.BUY,
            value=shares,
            style="shares",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def buy_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> TradeResult:
        """按资金比例买入."""
        return await self._submit_legacy_order(
            asset=asset,
            side=OrderSide.BUY,
            value=percent,
            style="percent",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def buy_amount(
        self,
        asset: str,
        amount: int | float,
        price: int | float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> TradeResult:
        """按金额买入."""
        return await self._submit_legacy_order(
            asset=asset,
            side=OrderSide.BUY,
            value=amount,
            style="amount",
            price=float(price),
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> TradeResult:
        """按股数卖出."""
        return await self._submit_legacy_order(
            asset=asset,
            side=OrderSide.SELL,
            value=shares,
            style="shares",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def sell_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> TradeResult:
        """按持仓比例卖出."""
        return await self._submit_legacy_order(
            asset=asset,
            side=OrderSide.SELL,
            value=percent,
            style="percent",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def sell_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> TradeResult:
        """按金额卖出."""
        return await self._submit_legacy_order(
            asset=asset,
            side=OrderSide.SELL,
            value=amount,
            style="amount",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def cancel_order(self, qt_oid: str):
        """撤销指定订单."""
        await self._adapter.cancel(qt_oid)

    async def cancel_all_orders(self, side: OrderSide | None = None):
        """撤销全部未完成订单."""
        await self._adapter.cancel_all(side=side)

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
    ) -> TradeResult:
        """将仓位调整到目标占比."""
        current_mv = 0.0
        for position in self.positions.values():
            if position.asset == asset:
                current_mv = float(position.mv)
                break
        total_asset = float(self.asset.total)
        if total_asset <= 0:
            return TradeResult.empty()
        target_mv = total_asset * target_pct
        side = OrderSide.BUY if target_mv >= current_mv else OrderSide.SELL
        return await self._submit_legacy_order(
            asset=asset,
            side=side,
            value=target_pct,
            style="target_pct",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra={},
        )

    async def _submit_legacy_order(
        self,
        asset: str,
        side: OrderSide,
        value: int | float,
        style: str,
        price: float,
        order_time: datetime.datetime | None,
        timeout: float,
        extra: dict[str, Any],
    ) -> TradeResult:
        """将旧版 Broker 调用委托到统一交易端口.

        当 ``strategy_runtime_config.cheat_on_close=False``（盘后决策模式）且
        broker 处于 live 模式时，订单**不**立即发送 qmt-gateway，而是放进
        :attr:`deferred_orders` 队列，调度器在次日指定时间调
        :meth:`process_deferred_orders` 时再下柜台（限价单，昨收/今开 + 滑点）。
        """
        if not self._strategy_cheat_on_close:
            scheduled_at = self._compute_scheduled_at()
            self._deferred_orders.append(
                {
                    "asset": asset,
                    "side": side,
                    "value": float(value),
                    "style": style,
                    "price": price,
                    "order_time": order_time,
                    "timeout": timeout,
                    "extra": extra,
                    "execution_window": self._live_execution_window,
                    "slippage": self._live_execution_slippage,
                    "scheduled_at": scheduled_at,
                    "submitted_at": self._now(),
                }
            )
            return TradeResult.empty()

        request = OrderRequest(
            asset=asset,
            side=side,
            value=float(value),
            style=style,
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=extra,
        )
        ack = await self._adapter.submit(request)
        if ack.order_id is None:
            return TradeResult.empty()
        trades = [
            Trade(
                self._portfolio_id,
                str(item.trade_id),
                str(item.order_id),
                "",
                str(item.asset),
                float(item.shares),
                float(item.price),
                float(item.amount),
                item.tm,
                OrderSide.BUY if side == OrderSide.BUY else OrderSide.SELL,
                "",
            )
            for item in (ack.trades or [])
        ]
        return TradeResult(str(ack.order_id), trades)

    def _now(self) -> datetime.datetime:
        if self._clock is not None:
            return self._clock
        return datetime.datetime.now()

    def _compute_scheduled_at(self) -> datetime.datetime:
        """根据 live_execution_window 算次日撮合时刻."""
        try:
            next_trade_date = calendar.day_shift(self._today(), 1)
        except Exception:
            next_trade_date = self._today() + datetime.timedelta(days=1)
        if self._live_execution_window == "post_auction":
            return datetime.datetime.combine(
                next_trade_date, datetime.time(9, 30, 0, 1000)
            )
        return datetime.datetime.combine(next_trade_date, datetime.time(9, 25))

    async def process_deferred_orders(
        self, now: datetime.datetime | None = None
    ) -> int:
        """扫描 :attr:`deferred_orders`，到点的订单按限价单下柜台.

        返回本次实际提交的订单数。scheduler 协程（或测试）按需调。
        """
        current = now or self._now()
        submitted = 0
        remaining: list[dict[str, Any]] = []
        for order in self._deferred_orders:
            if order["scheduled_at"] <= current:
                limit_price = self._estimate_limit_price(order)
                request = OrderRequest(
                    asset=order["asset"],
                    side=order["side"],
                    value=order["value"],
                    style=order["style"],
                    price=limit_price,
                    order_time=current,
                    timeout=order["timeout"],
                    extra={
                        **order["extra"],
                        "bid_type": "LIMIT",
                        "slippage": order["slippage"],
                        "execution_window": order["execution_window"],
                    },
                )
                ack = await self._adapter.submit(request)
                if ack.order_id is not None:
                    submitted += 1
            else:
                remaining.append(order)
        self._deferred_orders = remaining
        return submitted

    def _estimate_limit_price(self, order: dict[str, Any]) -> float:
        """限价单价格估算：auction 模式用昨收 + 滑点，post_auction 模式用今开 + 滑点."""
        try:
            trade_date = calendar.day_shift(self._today(), -1)
            hist = daily_bars.get_bars(
                n=2, end=trade_date, assets=[order["asset"]]
            )
            if hist is None or hist.is_empty():
                base_price = 0.0
            else:
                row = hist.row(-1, named=True)
                base_price = float(row.get("close", 0.0) or 0.0)
        except Exception:
            base_price = 0.0
        if base_price <= 0:
            base_price = float(order.get("price", 0.0) or 0.0)
        if base_price <= 0:
            return 0.0
        slippage = float(order.get("slippage", 0.0) or 0.0)
        return round(base_price * (1.0 + slippage), 4)


class GatewayBrokerAdapter(BrokerPort):
    """基于 qmt-gateway REST 的交易适配器."""

    def __init__(self, client: GatewayClient):
        """初始化适配器.

        Args:
            client: gateway 客户端。
        """
        self._client = client
        self._qtoid_to_external_order_id: dict[str, str] = {}
        self._external_order_id_to_qtoid: dict[str, str] = {}

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict | None = None,
    ) -> None:
        """记录策略运行数据.

        gateway 当前仅提供交易与查询能力，不在此端口持久化指标。
        """

    async def buy(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> ExecutionResult:
        """按股数买入."""
        return await self._submit_execution(
            asset=asset,
            side=OrderSide.BUY,
            value=shares,
            style="shares",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def buy_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> ExecutionResult:
        """按比例买入."""
        return await self._submit_execution(
            asset=asset,
            side=OrderSide.BUY,
            value=percent,
            style="percent",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def buy_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> ExecutionResult:
        """按金额买入."""
        return await self._submit_execution(
            asset=asset,
            side=OrderSide.BUY,
            value=amount,
            style="amount",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def sell(
        self,
        asset: str,
        shares: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> ExecutionResult:
        """按股数卖出."""
        return await self._submit_execution(
            asset=asset,
            side=OrderSide.SELL,
            value=shares,
            style="shares",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def sell_percent(
        self,
        asset: str,
        percent: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> ExecutionResult:
        """按比例卖出."""
        return await self._submit_execution(
            asset=asset,
            side=OrderSide.SELL,
            value=percent,
            style="percent",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def sell_amount(
        self,
        asset: str,
        amount: int | float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> ExecutionResult:
        """按金额卖出."""
        return await self._submit_execution(
            asset=asset,
            side=OrderSide.SELL,
            value=amount,
            style="amount",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs,
    ) -> ExecutionResult:
        """调整目标仓位占比."""
        asset_view = self.query_assets()
        if asset_view is None or asset_view.total <= 0:
            return ExecutionResult.empty()
        current_mv = 0.0
        for position in self.query_positions():
            if position.asset == asset:
                current_mv = float(position.mv)
                break
        target_mv = float(asset_view.total) * target_pct
        side = OrderSide.BUY if target_mv >= current_mv else OrderSide.SELL
        return await self._submit_execution(
            asset=asset,
            side=side,
            value=target_pct,
            style="target_pct",
            price=price,
            order_time=order_time,
            timeout=timeout,
            extra=kwargs,
        )

    async def submit(self, request: OrderRequest) -> OrderAck:
        """提交订单."""
        price = self._resolve_price(request)
        sizing_price = self._resolve_sizing_price(request, price)
        shares = self._resolve_shares(request, sizing_price)
        qtoid = str(request.extra.get("qtoid") or uuid4())
        strategy_id = str(request.extra.get("strategy_id") or "")
        if shares <= 0:
            return OrderAck(order_id=None, status="rejected", message="invalid shares")
        if request.side == OrderSide.BUY:
            payload = {
                "symbol": request.asset,
                "price": price,
                "shares": int(shares),
                "strategy_id": strategy_id,
                "qtoid": qtoid,
            }
            result = self._client.post_form("/api/trade/buy", payload) or {}
        else:
            payload = {
                "symbol": request.asset,
                "price": price,
                "shares": int(shares),
                "strategy_id": strategy_id,
                "qtoid": qtoid,
            }
            result = self._client.post_form("/api/trade/sell", payload) or {}
        if result.get("success"):
            response_qtoid = self._read_text(result, "qtoid")
            external_order_id = self._read_text(result, "order_id", "foid", "external_order_id")
            if response_qtoid and response_qtoid != qtoid:
                raise GatewayTradeStateConsistencyError(
                    "gateway submit returned mismatched qtoid; treat as block candidate"
                )
            self._remember_order_mapping(qtoid=qtoid, external_order_id=external_order_id)
            return OrderAck(
                order_id=qtoid,
                status="submitted",
                message="ok",
            )
        return OrderAck(
            order_id=None,
            status="rejected",
            message=str(result.get("error") or "gateway submit failed"),
        )

    async def cancel(self, order_id: str) -> CancelAck:
        """撤销订单."""
        result = self._client.post_form("/api/trade/cancel", {"qtoid": order_id}) or {}
        return CancelAck(
            success=bool(result.get("success", False)),
            message=str(result.get("error") or ""),
        )

    async def _submit_execution(
        self,
        asset: str,
        side: OrderSide,
        value: int | float,
        style: str,
        price: float,
        order_time: datetime.datetime | None,
        timeout: float,
        extra: dict[str, Any],
    ) -> ExecutionResult:
        """提交高阶交易请求并返回正式结果对象."""
        ack = await self.submit(
            OrderRequest(
                asset=asset,
                side=side,
                value=float(value),
                style=style,
                price=price,
                order_time=order_time,
                timeout=timeout,
                extra=extra,
            )
        )
        return ExecutionResult(
            order_id=ack.order_id,
            trades=list(ack.trades or []),
            status=ack.status,
            message=ack.message,
        )

    async def cancel_all(self, side: OrderSide | None = None) -> int:
        """撤销全部订单."""
        orders = self.query_orders()
        count = 0
        for order in orders:
            if side and not self._side_matches(order.side, side):
                continue
            if order.order_id:
                ack = await self.cancel(order.order_id)
                if ack.success:
                    count += 1
        return count

    def query_positions(self) -> list[PositionView]:
        """查询持仓."""
        rows = self._client.get_json("/api/trade/positions") or []
        result: list[PositionView] = []
        today = datetime.date.today()
        for row in rows:
            result.append(
                PositionView(
                    asset=str(row.get("symbol") or ""),
                    shares=float(row.get("shares") or 0),
                    avail=float(row.get("avail") or 0),
                    price=float(row.get("cost") or 0),
                    mv=float(row.get("market_value") or 0),
                    dt=today,
                )
            )
        return result

    def query_assets(self) -> AssetView | None:
        """查询资产."""
        row = self._client.get_json("/api/trade/asset") or {}
        if not row:
            return None
        today = datetime.date.today()
        return AssetView(
            cash=float(row.get("cash") or 0),
            total=float(row.get("total") or 0),
            market_value=float(row.get("market_value") or 0),
            frozen_cash=float(row.get("frozen_cash") or 0),
            principal=float(row.get("principal") or 0),
            dt=today,
        )

    def query_orders(self, status: str | None = None) -> list[OrderView]:
        """查询订单."""
        params = {"status": status} if status else None
        rows = self._client.get_json("/api/trade/orders", params=params) or []
        result: list[OrderView] = []
        for row in rows:
            qtoid = self._resolve_qtoid(row, context="query_orders")
            result.append(
                OrderView(
                    order_id=qtoid,
                    asset=str(row.get("symbol") or ""),
                    side=str(row.get("side") or ""),
                    shares=float(row.get("shares") or 0),
                    price=float(row.get("price") or 0),
                    status=str(row.get("status") or ""),
                    tm=self._parse_time_text(str(row.get("time") or "")),
                    filled=float(row.get("filled") or 0),
                    error="",
                )
            )
        return result

    def query_trades(self, order_id: str | None = None) -> list[TradeView]:
        """查询成交."""
        rows = self._client.get_json("/api/trade/trades") or []
        result: list[TradeView] = []
        for idx, row in enumerate(rows):
            trade_id = str(row.get("tid") or f"gw-{idx}")
            qtoid = self._resolve_qtoid(
                row,
                requested_qtoid=order_id,
                context="query_trades",
            )
            result.append(
                TradeView(
                    trade_id=trade_id,
                    order_id=qtoid,
                    asset=str(row.get("symbol") or ""),
                    side=str(row.get("side") or ""),
                    shares=float(row.get("shares") or 0),
                    price=float(row.get("price") or 0),
                    amount=float(row.get("amount") or 0),
                    tm=self._parse_time_text(str(row.get("time") or "")),
                )
            )
        return result

    def _resolve_price(self, request: OrderRequest) -> float:
        """解析正式下单价格，优先使用显式价格，其次回退到 live_quote 行情。"""
        if request.price > 0:
            return float(request.price)
        try:
            quote = live_quote.get_quote(request.asset)
        except Exception:
            return 0.0
        if not quote:
            return 0.0
        for key in ("price", "open", "high", "low"):
            value = quote.get(key)
            if value and value > 0:
                return float(value)
        return 0.0

    def _resolve_sizing_price(self, request: OrderRequest, execution_price: float) -> float:
        """解析金额类下单的数量估算价格，优先使用涨跌停保护价。"""
        try:
            down_limit, up_limit = live_quote.get_price_limits(request.asset)
        except Exception:
            return execution_price
        if request.side == OrderSide.BUY and up_limit and up_limit > 0:
            return float(up_limit)
        if request.side == OrderSide.SELL and down_limit and down_limit > 0:
            return float(down_limit)
        return execution_price

    def _resolve_shares(self, request: OrderRequest, price: float) -> int:
        """将统一下单请求转换为股数."""
        if request.style == "shares":
            return int(request.value // 100 * 100)
        if price <= 0:
            return 0
        if request.style == "amount":
            return int((request.value / price) // 100 * 100)
        if request.style == "percent":
            asset = self.query_assets()
            if asset is None:
                return 0
            amount = asset.total * request.value
            return int((amount / price) // 100 * 100)
        if request.style == "target_pct":
            asset = self.query_assets()
            if asset is None:
                return 0
            target_value = asset.total * request.value
            current_value = 0.0
            for position in self.query_positions():
                if position.asset == request.asset:
                    current_value = position.shares * price
                    break
            delta = target_value - current_value
            if request.side == OrderSide.BUY:
                if delta <= 0:
                    return 0
                return int((delta / price) // 100 * 100)
            if delta >= 0:
                return 0
            return int(((-delta) / price) // 100 * 100)
        return 0

    def _side_matches(self, text: str, side: OrderSide) -> bool:
        """判断订单方向是否匹配."""
        raw = str(text).strip().lower()
        if side == OrderSide.BUY:
            return raw in {"buy", "1", "买入"}
        if side == OrderSide.SELL:
            return raw in {"sell", "-1", "卖出"}
        return False

    def _remember_order_mapping(self, qtoid: str, external_order_id: str | None) -> None:
        """Record gateway external order-id mapping without replacing qtoid."""
        if not external_order_id or external_order_id == qtoid:
            return
        existing_qtoid = self._external_order_id_to_qtoid.get(external_order_id)
        if existing_qtoid and existing_qtoid != qtoid:
            raise GatewayTradeStateConsistencyError(
                "gateway external order id remapped to another qtoid; treat as block candidate"
            )
        existing_external = self._qtoid_to_external_order_id.get(qtoid)
        if existing_external and existing_external != external_order_id:
            raise GatewayTradeStateConsistencyError(
                "gateway qtoid remapped to another external order id; treat as block candidate"
            )
        self._qtoid_to_external_order_id[qtoid] = external_order_id
        self._external_order_id_to_qtoid[external_order_id] = qtoid

    def _resolve_qtoid(
        self,
        payload: dict[str, Any],
        requested_qtoid: str | None = None,
        *,
        context: str,
    ) -> str:
        """Resolve the canonical qtoid for gateway payloads."""
        qtoid = self._read_text(payload, "qtoid")
        external_order_id = self._read_text(payload, "order_id", "foid", "external_order_id")
        mapped_qtoid = self._external_order_id_to_qtoid.get(external_order_id or "")

        if qtoid and external_order_id:
            self._remember_order_mapping(qtoid=qtoid, external_order_id=external_order_id)
            return qtoid

        if qtoid:
            if requested_qtoid and requested_qtoid != qtoid:
                raise GatewayTradeStateConsistencyError(
                    f"{context} returned qtoid different from requested qtoid; treat as block candidate"
                )
            return qtoid

        if mapped_qtoid:
            return mapped_qtoid

        if requested_qtoid:
            if external_order_id:
                self._remember_order_mapping(qtoid=requested_qtoid, external_order_id=external_order_id)
            return requested_qtoid

        raise GatewayTradeStateConsistencyError(
            f"{context} missing qtoid and known external mapping; treat as block candidate"
        )

    def _read_text(self, payload: dict[str, Any], *keys: str) -> str | None:
        """Read the first non-empty string value from a payload."""
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _parse_time_text(self, text: str) -> datetime.datetime:
        """解析时间字符串."""
        if not text:
            return datetime.datetime.now()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
            try:
                parsed = datetime.datetime.strptime(text, fmt)
                if fmt == "%H:%M:%S":
                    today = datetime.date.today()
                    return datetime.datetime.combine(today, parsed.time())
                return parsed
            except ValueError:
                continue
        return datetime.datetime.now()
