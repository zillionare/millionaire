"""仿真交易 Broker 实现.

本模块实现了 PaperBroker（兼容别名 SimulationBroker），用于仿真交易。
"""

import datetime
import json
from collections import defaultdict
from typing import Any

import polars as pl

from quantide.core.enums import (
    BrokerKind,
    FrameType,
    OrderSide,
    OrderStatus,
    Topics,
)
from quantide.core.errors import (
    LimitPrice,
)
from quantide.core.market_time import market_now
from quantide.core.message import msg_hub
from quantide.core.order_identity import client_order_id
from quantide.core.ports import MarketDataPort
from quantide.core.ports.broker import ExecutionResult
from quantide.core.ports.clock import ClockPort
from quantide.data.models import Asset, Order, Portfolio, Position, Trade
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.abstract_broker import AbstractBroker
from quantide.service.bar_access import BarViewFacade
from quantide.service.bar_views import LiveBarView
from quantide.service.market_data_hub import market_data_hub
from quantide.service.paper_history import PaperHistory
from quantide.service.paper_matching import PaperMatching
from quantide.service.paper_orders import PaperOrders
from quantide.service.reference_prices import quote_prices


class PaperBroker(BarViewFacade, PaperMatching, PaperOrders, PaperHistory, AbstractBroker):
    """仿真交易 Broker。

    PaperBroker 模拟真实的交易环境，订阅实时行情，并在本地进行撮合。
    它维护自己的账户状态（现金、持仓），并将交易记录保存到数据库。
    """

    supports_idempotent_orders = True

    def find_order_by_client_id(self, identity: str) -> Order | None:
        """Return an accepted order after restart without submitting it again."""
        order = db.get_order(identity)
        if order is not None and order.portfolio_id != self.portfolio_id:
            raise ValueError("Order identity belongs to another portfolio")
        return order

    def _existing_order_result(self) -> ExecutionResult | None:
        identity = client_order_id.get()
        if not identity or self.find_order_by_client_id(identity) is None:
            return None
        fills = db.query_trade(qtoid=identity)
        trades = [] if fills is None else [Trade(**row) for row in fills.to_dicts()]
        return ExecutionResult(qt_oid=identity, trades=trades)

    def __init__(
        self,
        portfolio_id: str,
        principal: float = 1_000_000,
        commission: float = 1e-4,
        stamp_tax: float = 0.001,
        transfer_fee: float = 0.0,
        min_commission: float = 5.0,
        slippage: float = 0.0,
        dry_run: bool = False,
        portfolio_name: str = "simulation",
        info: str = "",
        market_value_update_interval: float = 10.0,
        market_data: MarketDataPort | None = None,
        auction_epsilon: float = 0.001,
        clock: ClockPort | None = None,
    ) -> None:
        """初始化 PaperBroker。

        Args:
            portfolio_id: 账户ID
            principal: 初始资金
            commission: 佣金费率 (默认 1e-4 = 0.01%, A 股双边)
            stamp_tax: 印花税率 (默认 0.001 = 0.1%, A 股仅卖方, FR-180)
            transfer_fee: 过户费率 (默认 0, 双边)
            min_commission: 单笔最低佣金 (默认 5 元)
            slippage: 滑点 (比率, 默认 0.0, FR-200)
            dry_run: dry-run 模式 (默认 False, FR-440): True 时 buy/sell 记录信号不实际下单
            portfolio_name: 账户名称
            info: 账户描述信息
            market_value_update_interval: 持仓市值更新间隔（秒），默认10秒
            market_data: 行情端口实现
            auction_epsilon: 集合竞价限价容差（竞价价 × (1+eps)），默认 0.1%
        """
        super().__init__(
            portfolio_id=portfolio_id,
            principal=principal,
            commission=commission,
            kind=BrokerKind.SIMULATION,
            portfolio_name=portfolio_name,
            info=info,
        )
        self._active_orders = defaultdict(list)
        self._positions: dict[str, Position] = {}
        # 缓存订单的成交记录，用于在完全成交或取消时返回完整结果
        self._order_trades: dict[str, list[Trade]] = defaultdict(list)

        self._market_value_update_interval = market_value_update_interval
        self._last_mv_update_time = 0.0
        self._market_data = market_data
        self._auction_epsilon = float(auction_epsilon)
        self._bar_view = LiveBarView(
            bars=daily_bars, market_data=market_data, today_func=self._get_today
        )
        self._stamp_tax = stamp_tax
        self._transfer_fee = transfer_fee
        self._min_commission = min_commission
        self._slippage = slippage
        self._dry_run = dry_run
        self._dry_run_signals: list[dict[str, Any]] = []
        self._limits: dict[str, dict[str, float]] = {}
        self._clock: datetime.datetime | None = None
        self._clock_port = clock
        self._closed = False
        self._restore_fee_config()

        # 初始化或加载状态
        self._init_or_sync_state()

        # 订阅行情
        self._quote_subscription = self._on_quote_update
        self._limit_subscription = self._on_limit_update
        msg_hub.subscribe(Topics.QUOTES_ALL.value, self._quote_subscription)
        msg_hub.subscribe(Topics.STOCK_LIMIT.value, self._limit_subscription)

    def close(self) -> None:
        """Release MessageHub subscriptions held by this broker.

        This method takes no inputs and returns ``None``. It is idempotent and
        prevents callbacks already queued by the MessageHub from mutating the
        broker after cleanup.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            msg_hub.unsubscribe(Topics.QUOTES_ALL.value, self._quote_subscription)
            msg_hub.unsubscribe(Topics.STOCK_LIMIT.value, self._limit_subscription)

    @classmethod
    def create(
        cls,
        portfolio_id: str,
        principal: float = 1_000_000,
        commission: float = 1e-4,
        stamp_tax: float = 0.001,
        transfer_fee: float = 0.0,
        min_commission: float = 5.0,
        slippage: float = 0.0,
        portfolio_name: str = "simulation",
        info: str = "",
        market_value_update_interval: float = 10.0,
        market_data: MarketDataPort | None = None,
        auction_epsilon: float = 0.001,
        clock: ClockPort | None = None,
    ) -> "PaperBroker":
        """创建新的 PaperBroker 实例。

        如果账户已存在，抛出异常。

        Args:
            portfolio_id: 账户ID
            principal: 初始资金
            commission: 佣金费率
            portfolio_name: 账户名称
            info: 账户描述信息
            market_value_update_interval: 持仓市值更新间隔（秒），默认10秒
            market_data: 行情端口实现
            auction_epsilon: 集合竞价限价容差（竞价价 × (1+eps)）

        Returns:
            PaperBroker 实例
        """
        if db.get_portfolio(portfolio_id):
            raise RuntimeError(f"Portfolio {portfolio_id} already exists. Use load().")

        broker = cls(
            portfolio_id=portfolio_id,
            principal=principal,
            commission=commission,
            stamp_tax=stamp_tax,
            transfer_fee=transfer_fee,
            min_commission=min_commission,
            slippage=slippage,
            portfolio_name=portfolio_name,
            info=info,
            market_value_update_interval=market_value_update_interval,
            market_data=market_data,
            auction_epsilon=auction_epsilon,
            clock=clock,
        )

        return broker

    @classmethod
    def load(
        cls,
        portfolio_id: str,
        market_data: MarketDataPort | None = None,
        clock: ClockPort | None = None,
    ) -> "PaperBroker":
        """加载已存在的 PaperBroker 实例。

        如果账户不存在，抛出异常。

        Args:
            portfolio_id: 账户ID
            market_data: 行情端口实现

        Returns:
            PaperBroker 实例
        """
        pf = db.get_portfolio(portfolio_id)
        if not pf:
            raise RuntimeError(f"Portfolio {portfolio_id} does not exist. Use create().")

        # 从数据库读取账户信息
        return cls(
            portfolio_id=portfolio_id,
            portfolio_name=pf.name or portfolio_id,
            info=pf.info or "",
            market_data=market_data,
            clock=clock,
        )

    def _restore_fee_config(self) -> None:
        table = db["paper_broker_settings"]
        table.create({"portfolio_id": str, "config": str}, pk="portfolio_id", if_not_exists=True)
        rows = list(table.rows_where("portfolio_id=?", (self.portfolio_id,)))
        if rows:
            config = json.loads(rows[0]["config"])
            for name, value in config.items():
                setattr(self, "_" + name, float(value))
        self._save_fee_config()

    def _save_fee_config(self) -> None:
        names = ("commission", "stamp_tax", "transfer_fee", "min_commission", "slippage")
        config = {name: getattr(self, "_" + name) for name in names}
        db["paper_broker_settings"].upsert(
            {"portfolio_id": self.portfolio_id, "config": json.dumps(config)}, pk="portfolio_id"
        )

    def apply_fee_config(
        self,
        *,
        commission: float | None = None,
        stamp_tax: float | None = None,
        transfer_fee: float | None = None,
        min_commission: float | None = None,
        slippage: float | None = None,
    ) -> None:
        """应用策略转仿真时保存的交易费用/滑点配置。"""
        if commission is not None:
            self._commission = float(commission)
        if stamp_tax is not None:
            self._stamp_tax = float(stamp_tax)
        if transfer_fee is not None:
            self._transfer_fee = float(transfer_fee)
        if min_commission is not None:
            self._min_commission = float(min_commission)
        if slippage is not None:
            self._slippage = float(slippage)
        self._save_fee_config()

    def _on_limit_update(self, data: dict[str, Any]) -> None:
        """涨跌停更新回调。

        SimBroker 通过 MarketDataHub 获取实时涨跌停数据。
        此处订阅主要为了保持架构一致性（所有外部数据均来自 MessageHub）。
        """
        with self._lock:
            if self._closed:
                return
            for asset, limits in data.items():
                if isinstance(limits, dict):
                    self._limits[asset] = {
                        "up": float(limits.get("up", limits.get("up_limit", 0)) or 0),
                        "down": float(limits.get("down", limits.get("down_limit", 0)) or 0),
                    }

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        return quote_prices(assets, self._get_quote)

    def _get_quote(self, asset: str) -> dict[str, Any] | None:
        """获取行情快照."""
        if self._market_data is not None:
            snap = self._market_data.snapshot([asset]).get(asset)
            if snap is not None:
                return {
                    "lastPrice": getattr(snap, "price", 0) or 0,
                    "open": getattr(snap, "open", 0) or 0,
                    "high": getattr(snap, "high", 0) or 0,
                    "low": getattr(snap, "low", 0) or 0,
                    "volume": getattr(snap, "volume", 0) or 0,
                    "amount": getattr(snap, "amount", 0) or 0,
                }
        return market_data_hub.get_quote(asset)

    def _in_auction(self, price: float) -> bool:
        """当前是否处于集合竞价撮合窗口。"""
        from quantide.service.execution_clock import execution_clock

        now = self._now()
        if now is None:
            return False
        return execution_clock.in_auction(now)

    def _auction_limit_price(self, price: float) -> float:
        """集合竞价的限价（竞价价 × (1+eps)）。"""
        from quantide.service.execution_clock import execution_clock

        return execution_clock.auction_price_limit(price, epsilon=self._auction_epsilon)

    def _reject_at_limit(self, asset: str, side: OrderSide) -> None:
        """Paper 不允许在涨停买入 / 跌停卖出（下单阶段直接拒绝）。"""
        quote = self._get_quote(asset)
        last_price = float(quote.get("lastPrice", 0) or 0) if quote else 0.0
        if last_price <= 0:
            return
        down_limit, up_limit = self._get_price_limits(asset)
        if side == OrderSide.BUY and up_limit > 0 and last_price >= up_limit:
            raise LimitPrice(asset, last_price)
        if side == OrderSide.SELL and down_limit > 0 and last_price <= down_limit:
            raise LimitPrice(asset, last_price)

    def _get_price_limits(self, asset: str) -> tuple[float, float]:
        """获取涨跌停价格.

        优先顺序：本地缓存 → MarketDataHub → 本地日线数据。
        涨跌停是日频静态数据，最后回落到本地存储，避免依赖实时行情源。
        """
        limits = self._limits.get(asset)
        if limits is not None:
            return limits["down"], limits["up"]
        # A supplied market-data port is authoritative for this broker.  An
        # absent quote means this isolated port has no limit data; do not
        # silently borrow a process-global/local-store limit.
        if self._market_data is not None:
            try:
                if not self._market_data.snapshot([asset]).get(asset):
                    return (0.0, 0.0)
            except Exception:
                return (0.0, 0.0)
        hub_limits = market_data_hub.get_limits(asset)
        if hub_limits != (0.0, 0.0):
            return hub_limits
        stored_limits = self._limits_from_limit_store(asset)
        if stored_limits != (0.0, 0.0):
            return stored_limits
        return self._limits_from_local_data(asset)

    def _limits_from_limit_store(self, asset: str) -> tuple[float, float]:
        """从当日 LimitPriceStore（Tushare 早晨发布）读取涨跌停价。"""
        try:
            from quantide.data import get_limit_price_store

            return get_limit_price_store().get_limits(asset, self._get_today())
        except Exception:  # pragma: no cover - 数据层未就绪
            return 0.0, 0.0

    def _limits_from_local_data(self, asset: str) -> tuple[float, float]:
        """从本地日线数据读取涨跌停价。"""
        try:
            from quantide.data.models.daily_bars import daily_bars

            return daily_bars.get_trade_price_limits(asset, self._get_today())
        except Exception:  # pragma: no cover - 数据层未就绪
            return 0.0, 0.0

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: FrameType | str = FrameType.DAY,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """获取 paper 模式策略所需的历史日线/分钟线数据。

        Issue #20：默认 ``include_forming_bar=True``，当 ``end_dt`` 落在今日且
        MarketDataHub 已收到今日 tick 时，合并今日 forming bar 在末尾；close/high/low
        反映盘中最新状态。

        Args:
            asset: 资产代码。
            count: 历史 bar 数量。
            end_dt: 截止时间，包含边界。
            frame_type: 周期类型，目前仅支持 ``1d``。
            include_forming_bar: 是否合并今日 forming bar（默认 True）。
                end_dt 早于今日时此参数无效。
        """
        # 委托给 LiveBarView：已完成日线/分钟线来自存储，forming bar 来自行情订阅中心。
        return self._bar_view.get_history(asset, count, end_dt, frame_type, include_forming_bar)

    def set_clock(self, dt: datetime.datetime | None) -> None:
        """设置当前仿真时钟。"""
        self._clock = dt

    def _now(self) -> datetime.datetime:
        if self._clock is not None:
            return self._clock
        clock = getattr(self, "_clock_port", None)
        return clock.now() if clock is not None else market_now()

    def _validate_data_consistency(self) -> None:
        """校验数据一致性。

        检查数据库中的 portfolio, asset, position 记录是否一致。

        Raises:
            RuntimeError: 如果发现数据不一致
        """
        pf = db.get_portfolio(self.portfolio_id)
        asset = db.get_asset(dt=None, portfolio_id=self.portfolio_id)
        positions_df = db.get_positions(dt=None, portfolio_id=self.portfolio_id)

        if pf is None:
            if asset is not None:
                raise RuntimeError(
                    "Data Inconsistency: Portfolio "
                    f"{self.portfolio_id}"
                    " missing but has asset records. Please clean up the database."
                )
            if not positions_df.is_empty():
                raise RuntimeError(
                    "Data Inconsistency: Portfolio "
                    f"{self.portfolio_id}"
                    " missing but has position records. Please clean up the database."
                )
        else:
            if asset is None:
                raise RuntimeError(
                    "Data Inconsistency: Portfolio "
                    f"{self.portfolio_id}"
                    " exists but has no asset records. Please clean up the database."
                )

    def _get_today(self) -> datetime.date:
        """获取当前日期。

        设计意图：
        虽然可以直接使用 datetime.date.today()，但在测试场景中，
        我们经常需要模拟“过去”或“未来”的时间点
        来验证跨日逻辑（如持仓结算、隔夜单处理）。使用 freezegun 等库 mock
        底层时间模块容易导致
        asyncio、Redis 客户端等依赖时间的组件出现死锁或行为异常。
        因此，这里封装一个专用的方法，以便在测试中通过 patch 简单安全地 mock 日期，
        而不影响系统其他部分。
        """
        return self._now().date()

    def _is_halted(self, asset: str) -> bool:
        """FR-170: 判定 asset 是否停牌 (volume == 0).

        quote 不存在视为未 setup (paper/live 推送前), 不阻止下单.
        只在显式 volume == 0 时判定为停牌.
        看 snap.volume 而非 quote["volume"] (后者经 `or 0` 把 None 转 0).
        """
        if self._market_data is None:
            return False
        snap = self._market_data.snapshot([asset]).get(asset)
        if snap is None:
            return False
        return bool(snap.volume == 0)

    @staticmethod
    def _floor_lot_size(shares: float) -> int:
        """买入数量向下取整到 100 整倍数 (FR-150).

        Returns:
            floor(shares / 100) * 100, 或 0 当 shares < 100.
        """
        return (int(shares) // 100) * 100

    def _settle_previous_sessions(self) -> None:
        """Recover T+1 availability even when the process missed the closing job."""
        today = self._get_today()
        with self._lock:
            for position in self._positions.values():
                if position.dt < today:
                    position.avail = position.shares
                    position.dt = today

    def settle_t1(self) -> None:
        """T+1 结算: 当日买入的 in-transit 持仓 (shares > avail) 在 day_end 后转为 avail

        (FR-160).

        维护 avail (可卖) + shares (总持仓) 分别记账; 调用此方法 (一般 day_end scheduler
        触发) 把当日 buy 的 in-transit shares 转入 avail.
        """
        for _asset, pos in self._positions.items():
            if pos.shares > pos.avail:
                pos.avail = pos.shares

    def _init_or_sync_state(self) -> None:
        """初始化或同步账户状态。

        如果在数据库中找不到对应的 portfolio，则创建新的。
        如果存在，则从数据库加载资产和持仓信息。
        """
        # 数据一致性检查
        self._validate_data_consistency()

        # 检查是否已有 portfolio 记录
        pf = db.get_portfolio(self.portfolio_id)
        # 检查资产记录
        asset = db.get_asset(dt=None, portfolio_id=self.portfolio_id)

        if not pf:
            # 创建新的 portfolio
            pf = Portfolio(
                portfolio_id=self.portfolio_id,
                kind=BrokerKind.SIMULATION,
                start=self._get_today(),
                name=self.portfolio_name,
                info=self.info,
                status=True,
            )
            db.insert_portfolio(pf)

        if asset:
            self._cash = asset.cash
            self._principal = asset.principal
        else:
            # 初始化资产
            asset = Asset.initial(self.portfolio_id, self._get_today(), self._principal)
            db.upsert_asset(asset)
            self._cash = self._principal

        # 同步持仓
        # 注意：这里需要加载最新的持仓，而不是所有历史记录
        # 按最新完整快照恢复，包括显式空仓快照。
        positions_df = db.get_positions(dt=None, portfolio_id=self.portfolio_id)

        if not positions_df.is_empty():
            for row in positions_df.to_dicts():
                pos = Position(**row)
                self._positions[pos.asset] = pos

        self._settle_previous_sessions()
        self._reconcile_position_costs_from_trades()
        self._restore_active_orders()

    def _restore_active_orders(self) -> None:
        """Rebuild the matching queue from committed order and fill facts."""
        orders = db.orders_all(portfolio_id=self.portfolio_id)
        if orders is None or orders.is_empty():
            return
        active = {
            OrderStatus.UNREPORTED,
            OrderStatus.WAIT_REPORTING,
            OrderStatus.REPORTED,
            OrderStatus.PART_SUCC,
        }
        for row in orders.to_dicts():
            order = Order(**row)
            if order.status not in active or order.filled >= order.shares:
                continue
            self._active_orders[order.asset].append(order)
            fills = db.query_trade(qtoid=order.qtoid)
            if fills is not None and not fills.is_empty():
                self._order_trades[order.qtoid] = [Trade(**item) for item in fills.to_dicts()]

    def _reconcile_position_costs_from_trades(self) -> None:
        """Restore fee-inclusive costs only when the full trade history agrees with holdings."""
        if not self._positions:
            return
        try:
            trades = db.trades_all(portfolio_id=self.portfolio_id)
        except Exception:
            return
        if trades is None or trades.is_empty():
            return
        try:
            trades = trades.sort("tm")
        except Exception:
            pass
        from quantide.data.trade_costs import position_costs

        costs = position_costs(trades.iter_rows(named=True))
        for asset, position in self._positions.items():
            shares, average = costs.get(asset, (0.0, 0.0))
            if shares > 0 and average > 0 and abs(shares - float(position.shares)) <= 1e-6:
                position.price = average

    @property
    def total_assets(self) -> float:
        """计算当前总资产（现金 + 持仓市值）。

        Returns:
            当前总资产
        """
        market_value = sum(p.mv for p in self._positions.values())
        return self._cash + market_value

    @property
    def positions(self) -> list[Position]:
        """获取当前持仓列表。"""
        return list(self._positions.values())

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def principal(self) -> float:
        return self._principal

        # 注意：卖出不影响剩余持仓的成本价 (pos.price)


SimulationBroker = PaperBroker
