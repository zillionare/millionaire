import asyncio
import datetime
import json
import threading
import time
from typing import Any

from loguru import logger

from quantide.core.enums import BrokerKind, OrderSide, OrderStatus
from quantide.core.errors import InsufficientPosition, NonMultipleOfLotSize
from quantide.core.ports.broker import (
    AssetView,
    CancelAck,
    ExecutionResult,
    OrderAck,
    OrderRequest,
    OrderView,
    PositionView,
)
from quantide.data.models import Position, StrategyLog, Trade
from quantide.data.sqlite import db
from quantide.service.backtest_logs import record_backtest_log


class AbstractBroker:
    """抽象 Broker 类。只实现超时控制功能，策略的 metrics 计算等功能"""

    def __init__(
        self,
        portfolio_id: str = "default",
        principal: float = 1_000_000,
        commission: float = 1e-4,
        kind: BrokerKind = BrokerKind.BACKTEST,
        portfolio_name: str = "",
        info: str = "",
        start: datetime.date | None = None,
        end: datetime.date | None = None,
    ):
        self._cash: float = principal
        self._portfolio_id: str = portfolio_id
        self._principal: float = principal
        self._commission: float = commission
        self._kind: BrokerKind = kind
        self._portfolio_name: str = portfolio_name
        self._info: str = info
        self._start: datetime.date | None = start
        self._end: datetime.date | None = end
        self._save_backtest_logs: bool = False

        # 超时等待队列，用来实现带超时的交易
        self._pending_txs: dict[Any, Any] = {}
        # 缓存尚未被wait的早期结果
        self._early_results: dict[Any, Any] = {}
        self._lock = threading.RLock()

    def as_date(self, dt: datetime.date | datetime.datetime) -> datetime.date:
        """将 datetime 转换为 date"""
        if isinstance(dt, datetime.datetime):
            return dt.date()
        return dt

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict | None = None,
    ) -> None:
        """记录策略运行数据

        Args:
            key: 数据名称
            value: 数据值
            dt: 时间，如果未指定则尝试使用仿真时间，否则使用当前时间
            extra: 额外信息
        """
        if dt is None:
            # 尝试获取仿真时间，如果没有则使用系统时间
            dt = datetime.datetime.now()

        extra_str = json.dumps(extra) if extra else ""

        log = StrategyLog(
            portfolio_id=self._portfolio_id,
            dt=dt,
            key=key,
            value=value,
            extra=extra_str
        )
        db.insert_strategy_logs(log)

    def write_backtest_log(
        self,
        level: str,
        source: str,
        message: str,
        dt: datetime.date | datetime.datetime | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        """记录回测文本日志。

        仅在 backtest 模式下生效，其它模式直接忽略。

        Args:
            level: 日志等级。
            source: 日志来源。
            message: 日志正文。
            dt: 日志时间。
            extra: 额外上下文。
        """
        if self._kind != BrokerKind.BACKTEST:
            return
        record_backtest_log(
            portfolio_id=self._portfolio_id,
            level=level,
            source=source,
            message=message,
            dt=dt,
            extra=extra,
            save_to_file=self._save_backtest_logs,
        )

    @property
    def portfolio_name(self) -> str:
        """Portfolio 对应的账户名称，是一个适合人类阅读的名字。一般应与 portfolio一一对应，不建议重复"""
        return self._portfolio_name

    @property
    def kind(self) -> BrokerKind:
        """Broker 类型"""
        return self._kind

    @property
    def info(self) -> str:
        """账户、策略的说明信息"""
        return self._info

    @property
    def portfolio_id(self) -> str:
        return self._portfolio_id

    def _validate_sell_shares(
        self, pos: Position, shares: float
    ) ->None:
        """卖出时，如果是清仓或零股 (不足一手的零散股) 则不限 100 整倍数；否则必须以 100 整数倍为单位 (FR-150)."""
        # 1. 基础检查：没有可用持仓
        if pos.avail == 0:
            raise InsufficientPosition(pos.asset, shares)

        # 2. 清仓判断:
        # 请求卖出的数量接近可用持仓量, 且可用持仓量接近总持仓量 (即全仓可卖)
        is_clearance = (abs(pos.shares - pos.avail) < 1e-7) and (abs(shares - pos.avail) < 1e-7)
        if is_clearance:
            return

        # 3. 零股判断 (FR-150 允许例外): 卖出数量 < 100 (零散股), 持仓 >= shares 即可
        # 例: 持仓 150 卖 50 (零股允许), 持仓 100 卖 50 不允许 (非清仓, 非零股)
        if shares < 100 and shares <= pos.avail:
            return

        # 4. 数量检查: 非清仓情况下, 卖出量不能超过可用量
        if shares > pos.avail:
             raise InsufficientPosition(pos.asset, shares)

        # 5. 整手检查
        if shares % 100 != 0 or shares == 0:
            raise NonMultipleOfLotSize(pos.asset, shares)

    async def wait(self, event_id: Any, timeout: float) -> tuple[Any, float]:
        """事件等待机制

        Args:
            event_id: 事件，全局唯一，通过它来获取绑定的 context
            timeout: 超时时间，单位秒。超时撮合不成功，返回空列表

        Returns:
            result: 事件结果。如果超时，则为 None
            remaining_time: 剩余时间，单位秒。如果超时，则为 0
        """
        with self._lock:
            # Check if result already arrived
            if event_id in self._early_results:
                return self._early_results.pop(event_id), 0.0

            if event_id in self._pending_txs:
                logger.warning("duplicate event_id: {}, overwritten.", event_id)

            _future = asyncio.get_running_loop().create_future()
            self._pending_txs[event_id] = _future

        try:
            t0 = time.perf_counter()
            result = await asyncio.wait_for(_future, timeout=timeout)
            return result, time.perf_counter() - t0
        except TimeoutError:
            with self._lock:
                self._pending_txs.pop(event_id, None)
            return None, 0

    def awake(self, event_id: Any, result: Any) -> None:
        """事件触发机制。线程安全。

        Args:
            event_id: 事件，全局唯一，通过它来获取绑定的 context
            result: 事件结果
        """
        with self._lock:
            if event_id in self._pending_txs:
                future = self._pending_txs.pop(event_id)
                if not future.done():
                    loop = future.get_loop()
                    if not loop.is_closed():
                        loop.call_soon_threadsafe(future.set_result, result)
            else:
                # Store for later
                self._early_results[event_id] = result

    # ---- BrokerPort Protocol 方法 ----

    async def submit(self, request: OrderRequest) -> OrderAck:
        """提交订单 (BrokerPort Protocol)."""
        try:
            result = await self._dispatch_submit(request)
            return OrderAck(
                qt_oid=result.qt_oid,
                status="submitted",
                trades=[t for t in (result.trades or []) if t is not None],
            )
        except Exception as exc:
            return OrderAck(qt_oid=None, status="rejected", message=str(exc))

    async def cancel(self, order_id: str) -> CancelAck:
        """撤销订单 (BrokerPort Protocol)."""
        try:
            await self.cancel_order(order_id)
            return CancelAck(success=True)
        except Exception as exc:
            return CancelAck(success=False, message=str(exc))

    async def cancel_all(self, side: OrderSide | None = None) -> int:
        """撤销全部订单 (BrokerPort Protocol).

        Returns:
            被撤销的订单数量。通过计算 cancel_all_orders 调用前的活跃订单数获得。
        """
        count = sum(
            1
            for orders in getattr(self, "_active_orders", {}).values()
            for o in orders
            if side is None or o.side == side
        )
        await self.cancel_all_orders(side=side)
        return count

    def query_positions(self) -> list[PositionView]:
        """查询持仓 (BrokerPort Protocol)."""
        result: list[PositionView] = []
        for pos in getattr(self, "_positions", {}).values():
            result.append(
                PositionView(
                    asset=pos.asset,
                    shares=float(pos.shares),
                    avail=float(pos.avail),
                    price=float(pos.price),
                    mv=float(pos.mv),
                    dt=pos.dt,
                )
            )
        return result

    def query_assets(self) -> AssetView | None:
        """查询资产 (BrokerPort Protocol)."""
        asset = db.get_asset(portfolio_id=self.portfolio_id)
        if asset is None:
            return None
        return AssetView(
            cash=float(asset.cash),
            total=float(asset.total),
            market_value=float(asset.market_value),
            frozen_cash=float(asset.frozen_cash),
            principal=float(asset.principal),
            dt=asset.dt,
        )

    def query_orders(self, status: str | None = None) -> list[OrderView]:
        """查询订单 (BrokerPort Protocol)."""
        df = db.get_orders(portfolio_id=self.portfolio_id)
        if df.is_empty():
            return []
        rows = df.to_dicts()
        if status:
            rows = [r for r in rows if self._status_matches(r.get("status"), status)]
        result: list[OrderView] = []
        for row in rows:
            result.append(
                OrderView(
                    order_id=str(row.get("qtoid") or ""),
                    asset=str(row.get("asset") or ""),
                    side=str(row.get("side") or ""),
                    shares=float(row.get("shares") or 0),
                    price=float(row.get("price") or 0),
                    status=str(row.get("status") or ""),
                    tm=self._to_datetime(row.get("tm")),
                    filled=float(row.get("filled") or 0),
                    error=str(row.get("error") or ""),
                )
            )
        return result

    def query_trades(self, order_id: str | None = None) -> list[Trade]:
        """查询成交 (BrokerPort Protocol)."""
        if order_id:
            df = db.query_trade(qtoid=order_id)
            if df is None or df.is_empty():
                return []
            rows = df.to_dicts()
        else:
            df = db.get_trades(portfolio_id=self.portfolio_id)
            if df.is_empty():
                return []
            rows = df.to_dicts()
        return [self._to_trade(row) for row in rows]

    async def _dispatch_submit(self, request: OrderRequest) -> ExecutionResult:
        """路由 OrderRequest 到具体的 buy/sell 方法."""
        if request.style == "shares":
            if request.side == OrderSide.BUY:
                return await self.buy(
                    asset=request.asset, shares=request.value,
                    price=request.price, order_time=request.order_time,
                    timeout=request.timeout,
                )
            return await self.sell(
                asset=request.asset, shares=request.value,
                price=request.price, order_time=request.order_time,
                timeout=request.timeout,
            )
        if request.style == "amount":
            if request.side == OrderSide.BUY:
                return await self.buy_amount(
                    asset=request.asset, amount=request.value,
                    price=request.price, order_time=request.order_time,
                    timeout=request.timeout,
                )
            return await self.sell_amount(
                asset=request.asset, amount=request.value,
                price=request.price, order_time=request.order_time,
                timeout=request.timeout,
            )
        if request.style == "percent":
            if request.side == OrderSide.BUY:
                return await self.buy_percent(
                    asset=request.asset, percent=request.value,
                    price=request.price, order_time=request.order_time,
                    timeout=request.timeout,
                )
            return await self.sell_percent(
                asset=request.asset, percent=request.value,
                price=request.price, order_time=request.order_time,
                timeout=request.timeout,
            )
        # target_pct
        return await self.trade_target_pct(
            asset=request.asset, target_pct=request.value,
            price=request.price, order_time=request.order_time,
            timeout=request.timeout,
        )

    def _status_matches(self, raw_status, expected: str) -> bool:
        """判断订单状态是否匹配."""
        text = str(expected).strip().upper()
        if text.isdigit():
            return str(raw_status) == text
        if isinstance(raw_status, int):
            try:
                return OrderStatus(raw_status).name == text
            except ValueError:
                return False
        return str(raw_status).upper() == text

    def _to_trade(self, trade) -> Trade:
        """转换 dict 或 Trade 为 Trade."""
        if isinstance(trade, Trade):
            return trade
        return Trade(
            tid=str(trade.get("tid") or ""),
            qtoid=str(trade.get("qtoid") or ""),
            foid="",
            asset=str(trade.get("asset") or ""),
            side=str(trade.get("side") or ""),
            shares=float(trade.get("shares") or 0),
            price=float(trade.get("price") or 0),
            amount=float(trade.get("amount") or 0),
            tm=self._to_datetime(trade.get("tm")),
            fee=float(trade.get("fee") or 0),
            cid="",
            portfolio_id=self.portfolio_id,
        )

    def _to_datetime(self, value):
        """将值转换为 datetime."""
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            return datetime.datetime.combine(value, datetime.time())
        if isinstance(value, str):
            return datetime.datetime.fromisoformat(value)
        return datetime.datetime.now()

