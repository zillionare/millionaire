import datetime
import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

import polars as pl
from loguru import logger

from quantide.core.enums import BrokerKind, OrderSide
from quantide.core.errors import (
    ClockAfterEnd,
    ClockBeforeStart,
    ClockRewind,
    DupPortfolio,
)
from quantide.data.models import Asset, Portfolio, Position
from quantide.data.models.calendar import calendar
from quantide.data.sqlite import db
from quantide.service.abstract_broker import AbstractBroker
from quantide.service.backtest_options import BacktestOptions
from quantide.service.backtest_orders import BacktestOrders
from quantide.service.backtest_snapshots import BacktestSnapshots
from quantide.service.bar_views import HistBarView
from quantide.service.datafeed import BarsFeedImpl


def _adjust_held_position_factors(
    held: dict[str, Position],
    factors: Mapping[str, Mapping[datetime.date, float]],
    prev_dt: datetime.date,
    new_dt: datetime.date,
) -> None:
    """Apply factor changes to each held position across a session boundary."""
    for asset, pos in held.items():
        values = factors.get(asset, {})
        prev_adjust = values.get(prev_dt)
        new_adjust = values.get(new_dt)
        if not prev_adjust or not new_adjust:
            continue
        ratio = new_adjust / prev_adjust
        if not math.isfinite(ratio) or ratio <= 0 or abs(ratio - 1.0) < 1e-12:
            continue
        old_shares = float(pos.shares)
        old_cost = float(pos.price)
        new_shares = int(round(old_shares * ratio))
        if new_shares <= 0:
            continue
        pos.shares = float(new_shares)
        # 取整后用总成本守恒反推每股成本，避免小数股残留。
        pos.price = old_shares * old_cost / new_shares


class BacktestBroker(BacktestSnapshots, BacktestOrders, AbstractBroker):
    interval: str

    def __init__(
        self,
        bt_start: datetime.date | datetime.datetime,
        bt_end: datetime.date | datetime.datetime,
        portfolio_id: str,
        data_feed: BarsFeedImpl,
        *legacy_options: object,
        options: BacktestOptions | None = None,
        **overrides: object,
    ) -> None:
        """Create a backtest broker, accepting established positional and keyword options.

        ``BacktestOptions`` documents the fee, matching and risk settings. Existing
        keyword arguments and their established positional order remain supported.
        """
        options = BacktestOptions.resolve(
            cast(Sequence[Any], legacy_options), options, cast(Mapping[str, Any], overrides)
        )
        self._initialize_backtest(bt_start, bt_end, portfolio_id, data_feed, options)

    def _initialize_backtest(
        self,
        bt_start: datetime.date | datetime.datetime,
        bt_end: datetime.date | datetime.datetime,
        portfolio_id: str,
        data_feed: BarsFeedImpl,
        options: BacktestOptions,
    ) -> None:
        """Initialize account, execution policy and snapshots from one named configuration."""
        super().__init__(
            portfolio_id=portfolio_id,
            principal=options.principal,
            commission=options.commission,
            portfolio_name=options.portfolio_name,
        )
        self._data_feed: BarsFeedImpl = data_feed
        self._minute_bars = options.minute_bars
        self._bar_view = HistBarView(data_feed, minute_bars=options.minute_bars)
        self._stamp_duty = max(0.0, float(options.stamp_duty))
        self._min_commission = max(0.0, float(options.min_commission))
        self._transfer_fee = max(0.0, float(options.transfer_fee))
        self._match_level = options.match_level
        self._bt_start: datetime.datetime = calendar.replace_time(bt_start, 9, 30)
        self._bt_end: datetime.datetime = calendar.replace_time(bt_end, 16, 0)
        self._bt_stopped: bool = False
        self._desc: str = options.desc
        self._save_backtest_logs = options.save_logs
        self._risk_overlay = options.risk_overlay
        self.allow_same_bar_repurchase = bool(options.allow_same_bar_repurchase)
        self._risk_overlay_in_progress = False
        self._risk_overlay_sold_assets: set[str] = set()
        self._auction_epsilon = max(0.0, float(options.auction_epsilon))
        prev = calendar.day_shift(bt_start, -1)
        if prev >= bt_start:
            frames = getattr(calendar, "day_frames", None)
            first_frame = frames[0] if frames is not None and len(frames) else None
            if first_frame is not None and hasattr(first_frame, "as_py"):
                first_frame = first_frame.as_py()
            has_earlier = bool(first_frame is not None and first_frame < bt_start)
            if has_earlier:
                raise ValueError(
                    f"交易日历异常：{bt_start} 的上一交易日为 {prev}，"
                    "请先完整同步交易日历（系统维护 → 数据维护 → 交易日历）"
                )
            prev = bt_start - datetime.timedelta(days=1)
        self._clock: datetime.datetime = calendar.replace_time(prev, 15)
        self.init_backtest()
        self._positions: dict[str, Position] = {}
        self._last_snapshot_day: datetime.date | None = None
        self.logger = logger.bind(portfolio_id=portfolio_id)

    @staticmethod
    def is_auction_time(tm: datetime.datetime) -> bool:
        """是否处于集合竞价窗口（14:57-15:00）。"""
        return datetime.time(14, 57) <= tm.time() <= datetime.time(15, 0)

    def _auction_bid_price(self, bars: pl.DataFrame, side: OrderSide) -> float:
        """集合竞价限价：竞价价（日线用收盘价近似）×(1±eps)。"""
        row = bars.row(0, named=True)
        base = float(row.get("close", 0.0) or 0.0)
        if base <= 0:
            return 0.0
        direction = 1.0 if side == OrderSide.BUY else -1.0
        return round(base * (1.0 + self._auction_epsilon * direction), 4)

    def _log(
        self,
        level: str,
        message: str,
        dt: datetime.date | datetime.datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """同时写入 loguru 与回测日志存储。"""
        log_dt = dt or self._clock
        self.logger.log(level.upper(), message)
        self.write_backtest_log(
            level=level,
            source="broker",
            message=message,
            dt=log_dt,
            extra=extra,
        )

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions

    def get_prices(self, assets: list[str]) -> dict[str, float]:
        """Risk overlays require a live/paper broker for current prices."""
        raise NotImplementedError("backtest broker does not provide live prices")

    def get_ticks(self, asset: str, count: int) -> pl.DataFrame:
        """Risk overlays require a live/paper broker for tick data."""
        raise NotImplementedError("backtest broker does not provide live ticks")

    @property
    def cash(self) -> float:
        return float(self._cash)

    def init_backtest(self) -> None:
        """创建回测相关数据记录

        在调用本方法时，数据库中不应该存在与本 portfolio 相关的 portfolios 和 assets 记录。
        """
        # 检查 portfolio 是否已存在
        if db.get_portfolio(self._portfolio_id):
            raise DupPortfolio(self._portfolio_id)

        # 检查 assets 表中是否已有该 portfolio 的记录
        if not db.query_assets(self._portfolio_id).is_empty():
            raise DupPortfolio(self._portfolio_id)

        portfolio = Portfolio(
            portfolio_id=self._portfolio_id,
            kind=BrokerKind.BACKTEST,
            start=self.as_date(self._clock),
            name=self._portfolio_name,
            info=self._desc,
            end=self.as_date(self._bt_end),
            status=True,
        )
        db.insert_portfolio(portfolio)

        # 记录回测前的资产，以便计算 day 0的收益，与 baseline 对齐
        asset = Asset.initial(self._portfolio_id, self.as_date(self._clock), self._principal)
        db.upsert_asset(asset)

    async def stop_backtest(self) -> None:
        """停止回测

        在停止回测时，需要模拟 bt_end 日，按收盘价卖出所有持仓的操作。
        注意：遵守 T+1 规则，仅卖出可用持仓 (avail > 0)。
        """
        # 1. 设置时钟到 bt_end，这会触发补齐逻辑，确保当前 positions 是最新的
        self.set_clock(self._bt_end)

        # 2. 遍历所有持仓并卖出可用部分
        order_time = self._bt_end
        # 获取当前所有持仓资产
        assets_to_sell = [a for a, p in self._positions.items() if p.avail > 0]

        try:
            for asset in assets_to_sell:
                pos = self._positions[asset]
                # 执行卖出。使用市价单 (price=0) 在 order_time (15:00) 撮合，将以收盘价成交
                try:
                    await self.sell(asset=asset, shares=pos.avail, price=0, order_time=order_time)
                except Exception as exc:
                    # 单个标的清仓失败（例如行情缺失、停牌）不应中断回测收尾
                    self._log(
                        "WARNING",
                        f"回测结束清仓失败: {asset} {exc}",
                        dt=order_time,
                    )

            # 3. 标记停止并更新数据库状态
            # 计算剩余持仓（冻结部分）的市值
            remaining_mv = self.market_value()

            dt = self.as_date(self._clock)
            asset_info = Asset(
                portfolio_id=self._portfolio_id,
                dt=dt,
                principal=self._principal,
                cash=self._cash,
                frozen_cash=0,
                market_value=remaining_mv,
                total=self._cash + remaining_mv,
            )
            db.upsert_asset(asset_info)
        finally:
            self._bt_stopped = True
            db.update_portfolio(self._portfolio_id, status=False)

    def get_bar_for_date(self, asset: str, date: datetime.date) -> dict[str, Any] | None:
        """Return the raw daily bar for ``asset`` on ``date`` if available."""
        try:
            df = self._data_feed.get_price_for_match(
                asset, datetime.datetime.combine(date, datetime.time(15, 0))
            )
        except Exception:
            return None
        if df is None or df.is_empty():
            return None
        return df.row(0, named=True)

    def get_bar_for_time(self, asset: str, tm: datetime.datetime) -> dict[str, Any] | None:
        """Return exactly the completed 30m bar at ``tm`` for risk overlays."""
        if self._minute_bars is None:
            return None
        value = tm.replace(tzinfo=None) if tm.tzinfo is not None else tm
        try:
            frame = self._minute_bars.get_bars_in_range(
                value, value, assets=[asset], adjust=None, eager_mode=True
            )
        except Exception:
            return None
        if frame is None or frame.is_empty():
            return None
        return cast(dict[str, Any] | None, frame.sort("date").row(0, named=True))

    def _price_for_match(
        self,
        asset: str,
        tm: datetime.datetime,
        fill_timing: str = "",
    ) -> pl.DataFrame | None:
        """Read the matching bar without falling back from 30m to daily data."""
        if self._match_level != "minute":
            return self._data_feed.get_price_for_match(asset, tm)
        if self._minute_bars is None:
            # Preserve the original minute-feed contract for callers that
            # provide minute data through the broker data feed.  The explicit
            # ``minute_bars`` source is used by 30m runtimes, where silently
            # falling back to daily data would be incorrect.
            return self._data_feed.get_price_for_match(asset, tm)
        value = tm.replace(tzinfo=None) if tm.tzinfo is not None else tm
        try:
            frame = self._minute_bars.get_bars_in_range(
                value.date(), value.date(), assets=[asset], adjust=None, eager_mode=True
            )
        except Exception:
            return None
        if frame is None or frame.is_empty():
            return None
        frame = frame.filter(pl.col("date") <= value).sort("date")
        if frame.is_empty():
            return None
        row = frame.tail(1)
        fill_col = "open" if fill_timing == "next_open" else "close"
        return cast(
            pl.DataFrame,
            row.with_columns(
                pl.col(fill_col).alias("price"),
                pl.col("date").alias("tm"),
            ),
        )

    async def run_risk_overlay(self, tm: datetime.datetime) -> None:
        """Check open gaps/time exits before the host's ``on_bar``."""
        if self._risk_overlay is None:
            return
        self._risk_overlay_in_progress = True
        try:
            await self._risk_overlay.check_open(self, tm)
        finally:
            self._risk_overlay_in_progress = False

    async def run_risk_overlay_intraday(self, tm: datetime.datetime) -> None:
        """Check same-day barrier touches after the host's ``on_bar``."""
        if self._risk_overlay is None:
            return
        self._risk_overlay_in_progress = True
        try:
            await self._risk_overlay.check_intraday(self, tm)
        finally:
            self._risk_overlay_in_progress = False

    def begin_risk_overlay_cycle(self) -> None:
        """Start a bar-scoped same-bar repurchase decision window."""
        self._risk_overlay_sold_assets.clear()

    def sync_risk_overlay(self, tm: datetime.datetime) -> None:
        """Register positions opened/changed by the host's ``on_bar``."""
        if self._risk_overlay is None:
            return
        self._risk_overlay.sync_positions(self._positions, self.as_date(tm))

    def set_clock(self, dt: datetime.datetime) -> None:
        """设置回测时钟。

        在设置回测时钟时，如果 dt 对应的日期与 self._clock 对应的日期不相同，则需要调用
        fill_history_gap 以填实跨越的日期 gap。
        """
        if dt < self._bt_start:
            raise ClockBeforeStart(dt, self._bt_start)
        if dt > self._bt_end:
            raise ClockAfterEnd(dt, self._bt_end)
        if dt < self._clock:
            raise ClockRewind(dt, self._clock)

        if not calendar.is_trade_day(self.as_date(dt)):
            self._log("WARNING", f"{dt} is not a valid trade day, skip set_clock", dt=dt)
            return

        new_dt = self.as_date(dt)
        old_dt = self.as_date(self._clock)

        if new_dt > old_dt:
            # 1. 执行展仓逻辑，填补从 clock 到 new_dt 前一天的缺失数据
            prev_dt = calendar.day_shift(new_dt, -1)
            self._fill_history_gaps(prev_dt)
            # 2. 把 new_dt 当日的除权比例落到内存持仓，保证当日 raw 价格与
            #    成本处于同一价格空间（不能等到 new_dt+1 展仓才调整）。
            self._apply_day_adjustment(new_dt, prev_dt)

            # 3. 内存状态迁移到新日期 (T+1 规则：所有持仓变为可用)
            for pos in self._positions.values():
                pos.avail = pos.shares
                pos.dt = new_dt

        self._clock = dt

    def _apply_day_adjustment(self, new_dt: datetime.date, prev_dt: datetime.date) -> None:
        """把当日除权比例应用到内存持仓（FR-185）.

        ``_fill_history_gaps`` 只结算到 ``prev_dt``，而 ``new_dt`` 的 raw 行情
        已经反映除权。若不在开盘前调整内存持仓，风控 overlay 会用「除权前成本」
        比较「除权后价格」，在送转/大额分红日产生假止损。这里按
        ``r = adjust(new_dt) / adjust(prev_dt)`` 同步股数与成本；市值/浮盈保持
        连续（拆股假设：现金分红视为再投资）。
        """
        held = {asset: pos for asset, pos in self._positions.items() if float(pos.shares or 0) > 0}
        if not held:
            return

        frame = self._get_close_adjust_factors(list(held), prev_dt, new_dt)
        if frame.is_empty():
            return

        factors: dict[str, dict[datetime.date, float]] = {}
        for row in frame.iter_rows(named=True):
            day = row["date"]
            if day not in (prev_dt, new_dt):
                continue
            adjust = float(row["adjust"] or 0.0)
            if adjust > 0 and math.isfinite(adjust):
                factors.setdefault(row["asset"], {})[day] = adjust

        _adjust_held_position_factors(held, factors, prev_dt, new_dt)
