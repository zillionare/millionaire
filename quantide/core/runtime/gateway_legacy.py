"""Legacy strategy/UI facade for the gateway BrokerPort."""

import datetime
from typing import Any, cast

import polars as pl

from quantide.core.enums import BidType, BrokerKind, FrameType, OrderSide
from quantide.core.ports import (
    BrokerPort,
    ExecutionResult,
)
from quantide.core.runtime.gateway_mapping import _coerce_order_side, _coerce_order_status
from quantide.core.runtime.order_convenience import (
    OrderConvenience,
    execution_request,
    target_order_side,
)
from quantide.data.helper import qfq_adjustment
from quantide.data.models import Asset, Order, Position, Trade
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.service.abstract_broker import AbstractBroker
from quantide.service.bar_access import (
    BarViewFacade,
    empty_history,
    history_end,
    previous_session,
    provider_history,
)
from quantide.service.market_data_hub import market_data_hub
from quantide.service.reference_prices import quote_prices


class GatewayBrokerWrapper(BarViewFacade, OrderConvenience, AbstractBroker):
    """将 GatewayBrokerAdapter 包装为旧版的 Broker 接口，以便 UI 使用。"""

    def __init__(
        self,
        adapter: BrokerPort,
        portfolio_id: str = "gateway",
    ) -> None:
        super().__init__(portfolio_id=portfolio_id, kind=BrokerKind.QMT)
        self._adapter = adapter
        self._portfolio_id = portfolio_id
        self._portfolio_name = "实盘网关"
        self._kind = BrokerKind.QMT
        self._clock: datetime.datetime | None = None
        self._strategy_cheat_on_close: bool = True
        self._live_execution_window: str = "auction"
        self._live_execution_slippage: float = 0.001
        self._deferred_orders: list[dict[str, Any]] = []
        from quantide.service.bar_views import LiveBarView

        self._bar_view = LiveBarView(
            bars=daily_bars,
            market_data=None,
            today_func=self._today,
        )

    def set_clock(self, dt: datetime.datetime | None) -> None:
        """设置当前策略时钟，便于 live 回放测试复用同一路径。"""
        self._clock = dt

    def set_strategy_runtime_config(
        self,
        cheat_on_close: bool = False,
        live_execution_window: str = "auction",
        live_execution_slippage: float = 0.001,
    ) -> None:
        """同步策略的收盘撮合、执行窗口和滑点参数。"""
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
        frame_type: FrameType | str = FrameType.DAY,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """获取 live 策略所需的历史日线数据。

        Issue #20：默认 ``include_forming_bar=True``，当 ``end_dt`` 落在今日且
        MarketDataHub 已收到今日 tick 时，合并今日 forming bar 在末尾；close/high/low
        反映盘中最新状态。
        """
        if frame_type not in (FrameType.DAY, "1d", "day"):
            raise NotImplementedError("GatewayBrokerWrapper currently only supports 1d history")
        frame_type = FrameType.DAY.value

        if not hasattr(daily_bars, "get_bars") and not hasattr(daily_bars, "get_history"):
            return self._empty_history_frame()
        end_date = self._resolve_history_end_date(end_dt)
        if not include_forming_bar and end_date == self._today():
            end_date = self._previous_trade_date(end_date)
            hist = self._provider_get_bars(daily_bars, asset, count, end_date, frame_type)
        else:
            hist = self._provider_get_bars(daily_bars, asset, count, end_date, frame_type)

        forming_applied = False
        if include_forming_bar:
            hist = self._maybe_attach_forming_bar(asset, hist, end_date, end_dt, count)
            forming_applied = True

        if not forming_applied and "adjust" in hist.columns and not hist.is_empty():
            hist = qfq_adjustment(hist, adj_factor_col="adjust", eager_mode=True)
        return hist

    def _provider_get_bars(
        self, provider: Any, asset: str, count: int, end_date: datetime.date, frame_type: str
    ) -> pl.DataFrame:
        frame = provider_history(provider, asset, count, end_date, frame_type, eager=True)
        return cast(pl.DataFrame, frame) if frame is not None else empty_history()

    def _maybe_attach_forming_bar(
        self,
        asset: str,
        hist: pl.DataFrame,
        end_date: datetime.date,
        end_dt: datetime.datetime | None,
        count: int,
    ) -> pl.DataFrame:
        """end_date==今日且 end_dt.time()>9:30 时，合并 MarketDataHub 的 forming bar.

        若 MarketDataHub 还没收到今日 tick（bar 为 None）— 今日的 close 还没固定，
        退回只看昨日及更早。
        """
        if end_date != self._today():
            return hist
        if isinstance(end_dt, datetime.datetime) and end_dt.time() <= datetime.time(9, 30):
            return hist
        bar = market_data_hub.get_daily_bar(asset)
        if bar is None:
            return self._provider_get_bars(
                getattr(self, "_history_provider", None) or daily_bars,
                asset,
                count,
                self._previous_trade_date(end_date),
                "1d",
            )
        bar_dt = bar.get("dt")
        if bar_dt is not None and hasattr(bar_dt, "date"):
            bar_dt = bar_dt.date()
        if bar_dt != end_date:
            return hist
        return self._concat_forming_with_history(hist, bar, count)

    @staticmethod
    def _concat_forming_with_history(
        hist: pl.DataFrame, forming: dict[str, Any], count: int
    ) -> pl.DataFrame:
        """共用 _concat_with_forming 逻辑（与 sim_broker 一致）。"""
        from quantide.service.sim_broker import PaperBroker

        return PaperBroker._concat_with_forming(hist, forming, count)

    def _previous_trade_date(self, today: datetime.date) -> datetime.date:
        return previous_session(calendar, today)

    def _resolve_history_end_date(self, end_dt: datetime.datetime | None) -> datetime.date:
        return cast(datetime.date, history_end(end_dt, self._today(), calendar))

    def _empty_history_frame(self) -> pl.DataFrame:
        return empty_history()

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
                tm=v.tm or datetime.datetime.combine(self._today(), datetime.time.min),
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
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录策略运行数据.

        Gateway 兼容层当前仅用于 UI 交易与查询，不持久化策略指标。
        """

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        return quote_prices(assets, market_data_hub.get_quote)

    async def cancel_order(self, qt_oid: str) -> None:
        """撤销指定订单."""
        await self._adapter.cancel(qt_oid)

    async def cancel_all_orders(self, side: OrderSide | None = None) -> None:
        """撤销全部未完成订单."""
        await self._adapter.cancel_all(side=side)

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
    ) -> ExecutionResult:
        """将仓位调整到目标占比."""
        total = float(self.asset.total)
        if total <= 0:
            return ExecutionResult.empty()
        side = target_order_side(asset, target_pct, total, self.positions.values())
        return await self._submit_legacy_order(
            asset, side, target_pct, "target_pct", price, order_time, timeout, {}
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
    ) -> ExecutionResult:
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
            return ExecutionResult.empty()

        request = execution_request(asset, side, value, style, price, order_time, timeout, extra)
        ack = await self._adapter.submit(request)
        if ack.order_id is None:
            return ExecutionResult.empty()
        trades = [
            Trade(
                self._portfolio_id,
                str(item.tid),
                str(item.qtoid),
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
        return ExecutionResult(qt_oid=str(ack.order_id), trades=trades)

    _submit_execution = _submit_legacy_order

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
            return datetime.datetime.combine(next_trade_date, datetime.time(9, 30, 0, 1000))
        return datetime.datetime.combine(next_trade_date, datetime.time(9, 25))

    async def process_deferred_orders(self, now: datetime.datetime | None = None) -> int:
        """扫描 :attr:`deferred_orders`，到点的订单按限价单下柜台.

        返回本次实际提交的订单数。scheduler 协程（或测试）按需调。
        """
        current = now or self._now()
        submitted = 0
        remaining: list[dict[str, Any]] = []
        for order in self._deferred_orders:
            if order["scheduled_at"] <= current:
                limit_price = self._estimate_limit_price(order)
                request = execution_request(
                    order["asset"],
                    order["side"],
                    order["value"],
                    order["style"],
                    limit_price,
                    current,
                    order["timeout"],
                    {
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
        """Estimate a deferred limit order from its scheduled reference session."""
        end_date, column = self._limit_price_reference(order)
        try:
            history = daily_bars.get_bars(n=2, end=end_date, assets=[order["asset"]])
            base = (
                float(history.row(-1, named=True).get(column, 0.0) or 0.0)
                if history is not None and not history.is_empty()
                else 0.0
            )
        except Exception:
            base = 0.0
        if base <= 0:
            base = float(order.get("price", 0.0) or 0.0)
        if base <= 0:
            return 0.0
        return round(base * (1.0 + float(order.get("slippage", 0.0) or 0.0)), 4)

    def _limit_price_reference(self, order: dict[str, Any]) -> tuple[datetime.date, str]:
        target = order.get("scheduled_at")
        if isinstance(target, datetime.datetime):
            target = target.date()
        if order.get("execution_window", "auction") == "post_auction":
            return target or self._today(), "open"
        if target is not None:
            return target - datetime.timedelta(days=1), "close"
        try:
            return calendar.day_shift(self._today(), -1), "close"
        except Exception:
            return self._today() - datetime.timedelta(days=1), "close"
