"""股票日线“视图”层。

把**已完结的日线**（持久化在 `daily_bars`）与**盘中 forming bar**（行情订阅中心/
实时行情源的最新快照）统一在一个接口下提供：

- `HistBarView`：仅已完结日线，用于回测；
- `LiveBarView`：已完结日线 + 今日 forming bar，用于 Paper 实盘。

设计原则：
1. 数据层不做任何时点冻结，也不落盘 forming bar；形成 bar 只在内存中拼装，
   策略按需一次性取走；
2. 只有当 `end_dt` 落在“今日且晚于 09:30”时才会注入 forming bar，否则与
   已完结日线完全一致；
3. 回测与实盘走同一套代码路径，回测侧永远不注入 forming bar。
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any, cast

import polars as pl

from quantide.core.bar_schema import (
    STANDARD_BAR_COLUMNS as STANDARD_BAR_COLUMNS,
)
from quantide.core.enums import FrameType
from quantide.data.models.calendar import calendar
from quantide.service.bar_access import (
    history_end,
    history_source,
    previous_session,
    provider_history,
)


def _snapshot_from_port(
    asset: str, self: LiveBarView, snapshot: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Snapshot from port."""
    if self._market_data is not None and hasattr(self._market_data, "snapshot"):
        try:
            snap = self._market_data.snapshot([asset]).get(asset)
        except Exception:
            snap = None
        if isinstance(snap, dict):
            snapshot = snap
        elif snap is not None:
            snapshot = {
                field: getattr(snap, field, None)
                for field in (
                    "price",
                    "open",
                    "high",
                    "low",
                    "volume",
                    "amount",
                    "ts",
                )
            }
    return snapshot


def _current_snapshot_price(snapshot: dict[str, Any] | None, today: datetime.date) -> float | None:
    """Reject absent prices and snapshots carrying another session's timestamp."""
    if not isinstance(snapshot, dict):
        return None
    price = snapshot.get("price")
    if price is None or price <= 0:
        price = snapshot.get("close")
    if price is None or price <= 0:
        return None
    stamp = snapshot.get("ts") or snapshot.get("dt")
    if stamp is not None:
        day = stamp.date() if hasattr(stamp, "date") else stamp
        if isinstance(day, datetime.datetime):
            day = day.date()
        if day != today:
            return None
    return cast(float, price)


class BarViewError(Exception):
    """行情视图错误。"""


class HistBarView:
    """已完结日线视图基类。

    提供两种读取方式：
    - `get_history`：单只股票的最近 n 根日线（策略 `get_bars` 走此路径）；
    - `get_bars_range`：多只股票的日期区间日线（策略面板选股/预取走此路径）。
    """

    def __init__(self, bars: Any = None, minute_bars: Any = None) -> None:
        from quantide.data.models.daily_bars import daily_bars
        from quantide.data.models.minute_bars import minute_bars as default_minute_bars

        self._bars = bars if bars is not None else daily_bars
        self._minute_bars = minute_bars if minute_bars is not None else default_minute_bars

    def _resolve_end_date(self, end_dt: datetime.datetime | None) -> datetime.date | None:
        return history_end(end_dt, None, calendar)

    def _fetch_completed(
        self, asset: str, count: int, end_date: datetime.date | None, frame_type: str = "1d"
    ) -> pl.DataFrame:
        return cast(
            pl.DataFrame, self._bars.get_bars(n=count, end=end_date, assets=[asset], adjust=None)
        )

    #: 兼容历史字符串写法
    _MINUTE_ALIASES = {
        "m30": FrameType.MIN30,
        "30": FrameType.MIN30,
        "30min": FrameType.MIN30,
        "m60": FrameType.MIN60,
        "60": FrameType.MIN60,
        "60min": FrameType.MIN60,
        "1h": FrameType.MIN60,
        "m15": FrameType.MIN15,
        "15": FrameType.MIN15,
        "15min": FrameType.MIN15,
        "m5": FrameType.MIN5,
        "5": FrameType.MIN5,
        "5min": FrameType.MIN5,
        "m1": FrameType.MIN1,
        "1": FrameType.MIN1,
        "1min": FrameType.MIN1,
    }

    @classmethod
    def _frame_type(cls, frame_type: FrameType | str | None) -> FrameType:
        """把字符串/枚举统一成 FrameType。"""
        if isinstance(frame_type, FrameType):
            return frame_type
        text = str(frame_type or "").strip()
        if not text:
            return FrameType.DAY
        lowered = text.lower()
        if lowered in cls._MINUTE_ALIASES:
            return cls._MINUTE_ALIASES[lowered]
        try:
            return FrameType(text)
        except ValueError as exc:
            raise NotImplementedError(f"BarView 不支持的周期: {frame_type}") from exc

    @classmethod
    def _minute_frame_type(cls, frame_type: FrameType | str | None) -> FrameType | None:
        """分钟周期返回对应 FrameType，否则返回 None。"""
        from quantide.data.models.calendar import calendar

        ft = cls._frame_type(frame_type)
        return ft if ft in calendar.minute_level_frames else None

    @staticmethod
    def _bucket_end(
        now: datetime.datetime, frame_type: FrameType = FrameType.MIN30
    ) -> datetime.datetime:
        """当前未完成桶的收盘时刻（Calendar 口径）。"""
        from quantide.data.models.calendar import calendar

        end = calendar.ceiling(now, frame_type)
        end = cast(datetime.datetime, end)
        return end.replace(tzinfo=None) if end.tzinfo is not None else end

    def get_minute_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: FrameType | str = FrameType.MIN30,
        include_forming_bar: bool = False,
    ) -> pl.DataFrame:
        """最近 n 根已完成分钟线（已关联复权因子/ST/涨跌停）。"""
        ft = self._minute_frame_type(frame_type)
        if ft is None:
            raise NotImplementedError(f"BarView 不是分钟周期: {frame_type}")
        if end_dt is None:
            end_dt = datetime.datetime.now()
        if end_dt.tzinfo is not None:
            end_dt = end_dt.replace(tzinfo=None)
        return cast(
            pl.DataFrame,
            self._minute_bars.get_bars(count, end=end_dt, assets=[asset], adjust="qfq"),
        )

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: FrameType | str = FrameType.DAY,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """最近 n 根已完成 bar（日线或分钟线）。"""
        ft = self._frame_type(frame_type)
        if self._minute_frame_type(ft) is not None:
            return self.get_minute_history(
                asset,
                count,
                end_dt,
                frame_type=ft,
                include_forming_bar=False,
            )
        if ft is not FrameType.DAY:
            raise NotImplementedError(f"BarView 不支持的历史周期: {frame_type}")
        end_date = self._resolve_end_date(end_dt)
        return self._fetch_completed(asset, count, end_date, ft.value)

    def get_bars_range(
        self,
        assets: list[str] | None,
        start_dt: datetime.datetime | datetime.date,
        end_dt: datetime.datetime | datetime.date | None = None,
        adjust: str | None = None,
        include_forming_bar: bool = False,
    ) -> pl.DataFrame:
        """指定日期区间的已完成日线（批量，一次扫描）。"""
        if end_dt is None:
            end_dt = start_dt
        end_date = end_dt.date() if isinstance(end_dt, datetime.datetime) else end_dt
        start_date = start_dt.date() if isinstance(start_dt, datetime.datetime) else start_dt
        df = cast(
            pl.DataFrame | None,
            self._bars.get_bars_in_range(
                start_date, end_date, assets=assets, adjust=adjust, eager_mode=True
            ),
        )
        if df is None or df.is_empty():
            return pl.DataFrame()
        return df.sort(["date", "asset"])


class LiveBarView(HistBarView):
    """带“收盘集合竞价 forming bar”的日线视图，用于 Paper 实盘。

    forming bar 来自唯一的行情订阅中心 `MarketDataHub`。
    """

    def __init__(
        self,
        bars: Any = None,
        market_data: Any = None,
        today_func: Callable[[], datetime.date] | None = None,
        minute_aggregator: Any = None,
    ) -> None:
        super().__init__(bars)
        self._market_data = market_data
        self._today_func = today_func
        self._minute_aggregator = minute_aggregator

    @property
    def _aggregator(self) -> Any:
        """盘中 30 分钟线合成器（默认全局单例）。"""
        if self._minute_aggregator is not None:
            return self._minute_aggregator
        from quantide.service.minute_bar_aggregator import minute_bar_aggregator

        return minute_bar_aggregator

    def _is_st(self, asset: str) -> bool:
        """ST 备份识别：Tushare 缺失时用发布者提供的名称。"""
        try:
            from quantide.service.market_data_hub import market_data_hub

            return market_data_hub.is_st(asset)
        except Exception:  # pragma: no cover - 数据层未就绪
            return False

    def _limits(self, asset: str) -> tuple[float, float]:
        """今日涨跌停价：行情端口/订阅中心优先，其次 Tushare 早晨落盘。"""
        market_data = self._market_data
        if market_data is not None and hasattr(market_data, "get_limits"):
            try:
                limits = cast(tuple[float, float], market_data.get_limits(asset))
                if limits != (0.0, 0.0):
                    return limits
            except Exception:  # pragma: no cover - 行情端口异常时回落
                pass
        from quantide.service.market_data_hub import market_data_hub

        limits = market_data_hub.get_limits(asset)
        if limits != (0.0, 0.0):
            return limits
        try:
            from quantide.data import get_limit_price_store

            stored = get_limit_price_store().get_limits(asset, self._today())
        except Exception:  # pragma: no cover - 数据层未就绪
            stored = (0.0, 0.0)
        if stored != (0.0, 0.0):
            return stored
        return 0.0, 0.0

    def _previous_raw_close(self, asset: str, day: datetime.date) -> float | None:
        """上一交易日的原始收盘价（用于识别除权日）。"""
        from quantide.data.models.calendar import calendar as market_calendar

        try:
            prev_day = market_calendar.day_shift(day, -1)
        except Exception:
            prev_day = day - datetime.timedelta(days=1)
        try:
            frame = cast(
                pl.DataFrame | None,
                self._bars.get_bars(n=1, end=prev_day, assets=[asset], adjust=None),
            )
        except Exception:
            return None
        if frame is None or frame.is_empty() or "close" not in frame.columns:
            return None
        if "date" in frame.columns:
            frame = frame.sort("date")
        value = frame["close"][-1]
        return float(value) if value else None

    def _today_basis_ratio(self, asset: str, day: datetime.date) -> float:
        """除权日盘中把历史复权价换算到今日基准的比例。

        交易所当天的昨收价已按除权除息调整，因此
        ``prev_close / 上一交易日原始收盘`` 就是今日因子相对昨日因子的比例。
        非除权日两者相等，返回 1.0。
        """
        snapshot = self._snapshot_for(asset)
        if not snapshot:
            return 1.0
        prev_close = snapshot.get("prev_close")
        raw_prev = self._previous_raw_close(asset, day)
        if not prev_close or not raw_prev:
            return 1.0
        ratio = float(prev_close) / float(raw_prev)
        if ratio <= 0 or abs(ratio - 1.0) <= 0.0002:
            return 1.0
        return ratio

    def _rebase_history_to_today(
        self,
        frame: pl.DataFrame,
        asset: str,
        day: datetime.date,
    ) -> pl.DataFrame:
        """把 ``day`` 之前的历史价格/量换算到今日复权基准（仅除权日生效）。"""
        if frame is None or frame.is_empty() or "date" not in frame.columns:
            return frame
        ratio = self._today_basis_ratio(asset, day)
        if ratio == 1.0:
            return frame
        mask = (pl.col("date").dt.date() < day) & (pl.col("asset") == asset)
        exprs = []
        for col in ("open", "high", "low", "close", "up_limit", "down_limit"):
            if col in frame.columns:
                exprs.append(
                    pl.when(mask).then(pl.col(col) * ratio).otherwise(pl.col(col)).alias(col)
                )
        if "volume" in frame.columns:
            exprs.append(
                pl.when(mask)
                .then(pl.col("volume") / ratio)
                .otherwise(pl.col("volume"))
                .alias("volume")
            )
        return frame.with_columns(exprs) if exprs else frame

    def _today(self) -> datetime.date:
        if self._today_func is not None:
            return self._today_func()
        return datetime.datetime.now().date()

    def _snapshot_for(self, asset: str) -> dict[str, Any] | None:
        """Build today's forming bar only from a usable, current snapshot."""
        snapshot = _snapshot_from_port(asset, self, None)
        if snapshot is None:
            from quantide.service.market_data_hub import market_data_hub

            snapshot = market_data_hub.get_daily_bar(asset)
        price = _current_snapshot_price(snapshot, self._today())
        if price is None or snapshot is None:
            return None
        down_limit, up_limit = self._limits(asset)
        return {
            "date": self._today(),
            "asset": asset,
            "open": snapshot.get("open") or price,
            "high": snapshot.get("high") or price,
            "low": snapshot.get("low") or price,
            "close": price,
            "volume": snapshot.get("volume") or 0,
            "amount": snapshot.get("amount") or 0,
            "adjust": 1.0,
            "is_st": bool(self._is_st(asset)),
            "up_limit": up_limit,
            "down_limit": down_limit,
            "prev_close": snapshot.get("prev_close"),
        }

    def _forming_rows(self, assets: list[str], today: datetime.date) -> pl.DataFrame:
        """把今日各标的的 forming bar 拼成 DataFrame。缺行情的标的直接跳过。"""
        rows: list[dict[str, Any]] = []
        for asset in assets:
            snap = self._snapshot_for(asset)
            if snap is not None:
                rows.append(snap)
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows)

    def _prev_trade_date(self, today: datetime.date) -> datetime.date:
        return previous_session(calendar, today)

    def _fetch_completed(
        self, asset: str, count: int, end_date: datetime.date | None, frame_type: str = "1d"
    ) -> pl.DataFrame:
        provider = history_source(self._market_data, self._bars)
        frame = provider_history(provider, asset, count, end_date, frame_type)
        return cast(pl.DataFrame, frame) if frame is not None else pl.DataFrame()

    def _inject_forming(
        self,
        completed: pl.DataFrame,
        end_dt: datetime.datetime | None,
        assets: list[str] | None,
        include_forming_bar: bool,
    ) -> pl.DataFrame:
        """把今日 forming bar 合进已完成日线；没有行情时返回已完成日线。"""
        if (
            not include_forming_bar
            or end_dt is None
            or end_dt.date() != self._today()
            or end_dt.time() <= datetime.time(9, 30)
        ):
            return completed
        today = self._today()
        date_col = (
            "date"
            if "date" in completed.columns
            else ("frame" if "frame" in completed.columns else None)
        )
        if date_col is None:
            return completed
        if date_col != "date":
            completed = completed.rename({date_col: "date"})
        assets = assets or completed["asset"].unique().to_list()
        forming = self._forming_rows(assets, today)
        if forming.is_empty():
            # 没有今日行情：按“昨日结束”处理，丢掉已完成部分的今日行（若有）
            completed = completed.filter(pl.col("date") < today)
            return completed
        forming = forming.with_columns(pl.col("date").cast(pl.Date))
        if "prev_close" in forming.columns:
            forming = forming.drop("prev_close")
        missing = [col for col in completed.columns if col not in forming.columns]
        if missing:
            forming = forming.with_columns([pl.lit(None).alias(col) for col in missing])
        forming = forming.select(completed.columns)
        merged = pl.concat([completed, forming], how="vertical_relaxed")
        completed = merged.unique(subset=["date", "asset"], keep="last").sort(["date", "asset"])
        return completed

    def _merge_aggregated_minute(
        self,
        completed: pl.DataFrame,
        asset: str,
        end_dt: datetime.datetime,
    ) -> pl.DataFrame:
        """把内存合成的当日已完成桶合进 BaoStock 历史（历史优先）。"""
        aggregator = self._aggregator
        try:
            aggregator.subscribe([asset])
            rows = aggregator.completed(asset, end=end_dt)
        except Exception:  # pragma: no cover - 合成器不可用时只返回历史
            return completed
        if not rows:
            return completed
        if completed is not None and not completed.is_empty():
            existing = set(completed["date"].to_list())
            rows = [row for row in rows if row["date"] not in existing]
        if not rows:
            return completed
        down_limit, up_limit = self._limits(asset)
        is_st = self._is_st(asset)
        today = pl.DataFrame(rows).with_columns(
            pl.col("date").cast(pl.Datetime("ms")),
            pl.lit(1.0).alias("adjust"),
            pl.lit(is_st).alias("is_st"),
            pl.lit(up_limit).alias("up_limit"),
            pl.lit(down_limit).alias("down_limit"),
        )
        if completed is None or completed.is_empty():
            return today
        today = today.select(completed.columns)
        return pl.concat([completed, today], how="vertical_relaxed")

    def _append_forming_minute(
        self,
        completed: pl.DataFrame,
        asset: str,
        end_dt: datetime.datetime,
    ) -> pl.DataFrame:
        """追加当前未完成桶（收盘时刻 > end_dt）。"""
        try:
            self._aggregator.subscribe([asset])
            row = self._aggregator.forming(asset, end_dt)
        except Exception:  # pragma: no cover - 合成器不可用时忽略
            return completed
        if row is None:
            return completed
        down_limit, up_limit = self._limits(asset)
        row = {
            **row,
            "adjust": 1.0,
            "is_st": self._is_st(asset),
            "up_limit": up_limit,
            "down_limit": down_limit,
        }
        forming = pl.DataFrame([row]).with_columns(pl.col("date").cast(pl.Datetime("ms")))
        if completed is None or completed.is_empty():
            return forming
        forming = forming.select(completed.columns)
        merged = pl.concat([completed, forming], how="vertical_relaxed")
        return merged.unique(subset=["date", "asset"], keep="last")

    def get_minute_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: FrameType | str = FrameType.MIN30,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        ft = self._minute_frame_type(frame_type)
        if ft is None:
            raise NotImplementedError(f"LiveBarView 不是分钟周期: {frame_type}")
        if end_dt is None:
            end_dt = datetime.datetime.now()
        if end_dt.tzinfo is not None:
            end_dt = end_dt.replace(tzinfo=None)
        completed = super().get_minute_history(
            asset, count, end_dt, frame_type=ft, include_forming_bar=False
        )
        if (
            end_dt.date() == self._today()
            and completed is not None
            and not completed.is_empty()
            and cast(datetime.datetime, completed["date"].max()).date() < end_dt.date()
        ):
            # 历史只到上一交易日：qfq 基准是昨日因子，需换算到今日基准。
            # 若存储已含今日数据（盘后同步）则基准已是今日因子，不能重复缩放。
            completed = self._rebase_history_to_today(completed, asset, end_dt.date())
        completed = self._merge_aggregated_minute(completed, asset, end_dt)
        if include_forming_bar and end_dt.time() > datetime.time(9, 30):
            completed = self._append_forming_minute(completed, asset, end_dt)
        if completed is None or completed.is_empty():
            return completed
        return completed.sort(["date", "asset"]).tail(int(count))

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: FrameType | str = FrameType.DAY,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        ft = self._frame_type(frame_type)
        if self._minute_frame_type(ft) is not None:
            return self.get_minute_history(
                asset,
                count,
                end_dt,
                frame_type=ft,
                include_forming_bar=include_forming_bar,
            )
        if ft is not FrameType.DAY:
            raise NotImplementedError(f"LiveBarView 不支持的历史周期: {frame_type}")
        end_date = self._resolve_end_date(end_dt)
        if not include_forming_bar and end_date == self._today():
            end_date = self._prev_trade_date(end_date)
        completed = self._fetch_completed(asset, count, end_date, ft.value)
        completed = self._inject_forming(completed, end_dt, [asset], include_forming_bar)
        return completed

    def get_bars_range(
        self,
        assets: list[str] | None,
        start_dt: datetime.datetime | datetime.date,
        end_dt: datetime.datetime | datetime.date | None = None,
        adjust: str | None = None,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        if end_dt is None:
            end_dt = start_dt
        end_date = end_dt.date() if isinstance(end_dt, datetime.datetime) else end_dt
        start_date = start_dt.date() if isinstance(start_dt, datetime.datetime) else start_dt
        completed = cast(
            pl.DataFrame | None,
            self._bars.get_bars_in_range(
                start_date, end_date, assets=assets, adjust=adjust, eager_mode=True
            ),
        )
        if completed is None or completed.is_empty():
            return pl.DataFrame()
        # get_bars_range 的 end_dt 常是 date；forming 注入需要带时间，
        # 用当日 15:00 作为收盘代表时刻。
        forming_dt = (
            end_dt
            if isinstance(end_dt, datetime.datetime)
            else datetime.datetime.combine(end_date, datetime.time(15, 0))
        )
        completed = self._inject_forming(
            completed,
            forming_dt,
            assets or completed["asset"].unique().to_list(),
            include_forming_bar,
        )
        return completed.sort(["date", "asset"])
