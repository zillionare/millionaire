"""盘中分钟线内存合成器。

历史分钟线只从 BaoStock 落盘（上一已收盘交易日起）；当日分钟线不落盘，
由本模块在交易时段内**每分钟采样一次实时行情**，在内存中合成 30 分钟线：

- 时间轴与项目 ``Calendar`` 一致：使用 **bar 收盘时刻** 作为索引
  （10:00 / 10:30 / 11:00 / 11:30 / 13:30 / 14:00 / 14:30 / 15:00）；
- 成交量/成交额用实时快照的**当日累计值做差**，得到每个桶的增量；
- 15:00 后合成结束；当日数据保留在内存中，直到数据同步把该日 BaoStock
  30 分钟线入库后由 ``clear_between`` 丢弃；
- 进程重启/盘中启动时只能从启动时刻开始合成，之前的桶无法恢复（这是
  “历史只信 BaoStock”的代价，避免用腾讯分钟线补历史而触发风控）。
"""

from __future__ import annotations

import datetime
import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol, cast

from loguru import logger

from quantide.core.domain.events import QuoteSnapshot
from quantide.core.enums import FrameType

#: 采样间隔（秒）
DEFAULT_SAMPLE_INTERVAL = 60.0
#: 上午/下午交易时段（含边界）
MORNING = (datetime.time(9, 30), datetime.time(11, 30))
AFTERNOON = (datetime.time(13, 0), datetime.time(15, 0))


def _naive(value: datetime.datetime) -> datetime.datetime:
    """去掉时区，统一存 naive 时间。"""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


class QuoteSource(Protocol):
    """Minimal snapshot source used by the aggregator."""

    def snapshot(self, symbols: list[str]) -> Mapping[str, QuoteSnapshot]:
        """Return the latest quote for each requested symbol."""
        ...


class CalendarPort(Protocol):
    """Calendar operations used by the aggregator."""

    def is_trade_day(self, dt: datetime.datetime) -> bool:
        """Return whether the date is a trading day."""
        ...

    def ceiling(
        self, moment: datetime.datetime, frame_type: FrameType
    ) -> datetime.datetime | datetime.date:
        """Return the end of the frame containing ``moment``."""
        ...


def _quote_field(quote: Mapping[str, object] | QuoteSnapshot, name: str) -> object:
    """Read a field from either a dict-like quote or a QuoteSnapshot."""
    """同时支持 dict 与 QuoteSnapshot。"""
    if isinstance(quote, Mapping):
        return quote.get(name)
    return cast(object, getattr(quote, name, None))


class MinuteBarAggregator:
    """把实时快照合成当日 30 分钟线（仅内存）。"""

    def __init__(
        self,
        market_data: QuoteSource | None = None,
        clock: Callable[[], datetime.datetime] | None = None,
        interval: float = DEFAULT_SAMPLE_INTERVAL,
        calendar: CalendarPort | None = None,
    ) -> None:
        self._market_data = market_data
        self._clock: Callable[[], datetime.datetime] = clock or datetime.datetime.now
        if calendar is None:
            from quantide.data.models.calendar import calendar as default_calendar

            calendar = default_calendar
        self._calendar = calendar
        self._interval = float(interval)
        self._assets: set[str] = set()
        self._completed: dict[datetime.date, dict[str, list[dict[str, Any]]]] = {}
        self._forming: dict[str, dict[str, Any]] = {}
        self._last_completed: dict[str, datetime.datetime] = {}
        self._last_cum: dict[str, tuple[float, float]] = {}
        self._last_cum_day: dict[str, datetime.date] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def subscribe(self, assets: list[str] | set[str]) -> None:
        """登记需要合成的标的（策略读取时自动调用）。"""
        with self._lock:
            self._assets.update(str(a) for a in assets if str(a).strip())

    def ensure_started(self) -> None:
        """确保后台采样线程已启动（无行情源时不启动）。"""
        if self._thread is not None and self._thread.is_alive():
            return
        if self._market_data is None:
            from quantide.service.market_data_hub import market_data_hub

            self._market_data = market_data_hub
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="minute-bar-aggregator", daemon=True
        )
        self._thread.start()
        logger.info("30 分钟线内存合成器已启动（每 {} 秒采样）", self._interval)

    def stop(self) -> None:
        """停止后台采样。"""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.sample_once()
            except Exception:  # pragma: no cover - 后台线程不能退出
                logger.exception("30 分钟线合成采样失败")

    # ------------------------------------------------------------------
    # 采样
    # ------------------------------------------------------------------
    @staticmethod
    def is_session(now: datetime.datetime) -> bool:
        """是否处于连续竞价时段（含 11:30/15:00 边界）。"""
        tm = now.time()
        return (MORNING[0] <= tm <= MORNING[1]) or (AFTERNOON[0] <= tm <= AFTERNOON[1])

    def sample_once(self, now: datetime.datetime | None = None) -> None:
        """采样一次：抓取已订阅标的的最新快照并更新内存 bar。"""
        now = _naive(now or self._clock())
        with self._lock:
            self._finalize_due(now)
            if not self.is_session(now) or not self._calendar.is_trade_day(now):
                return
            assets = sorted(self._assets)
        if not assets or self._market_data is None:
            return
        try:
            quotes = self._market_data.snapshot(assets)
        except Exception:
            logger.exception("读取实时行情失败")
            return
        with self._lock:
            for asset, quote in (quotes or {}).items():
                self.on_sample(str(asset), quote, now)

    def on_sample(
        self,
        asset: str,
        quote: Mapping[str, object] | QuoteSnapshot,
        now: datetime.datetime | None = None,
    ) -> None:
        """用一条快照更新某标的的当前 30 分钟桶（测试可直接调用）。"""
        now = _naive(now or self._clock())
        if not self.is_session(now) or not self._calendar.is_trade_day(now):
            return
        raw_price = _quote_field(quote, "price")
        if raw_price is None or float(cast(float | int | str, raw_price)) <= 0:
            return
        price = float(cast(float | int | str, raw_price))
        cum_volume = float(cast(float | int | str, _quote_field(quote, "volume") or 0.0))
        cum_amount = float(cast(float | int | str, _quote_field(quote, "amount") or 0.0))
        ts = _quote_field(quote, "ts")
        if isinstance(ts, datetime.datetime):
            ts = _naive(ts)
            sample_day = ts.date()
        else:
            sample_day = now.date()
        if sample_day != now.date():
            # 行情时间戳不是今天（收盘后残留），不参与合成。
            return
        bucket = _naive(cast(datetime.datetime, self._calendar.ceiling(now, FrameType.MIN30)))

        with self._lock:
            self._update(asset, price, cum_volume, cum_amount, bucket)

    def _update(
        self,
        asset: str,
        price: float,
        cum_volume: float,
        cum_amount: float,
        bucket: datetime.datetime,
    ) -> None:
        forming = self._forming.get(asset)
        if forming is not None:
            if bucket < forming["date"]:
                return
            if bucket > forming["date"]:
                self._complete(asset)
                forming = None
        if forming is None:
            if self._last_completed.get(asset, datetime.datetime.min) >= bucket:
                return
            same_day = self._last_cum_day.get(asset) == bucket.date()
            if same_day and asset in self._last_cum:
                base_volume, base_amount = self._last_cum[asset]
            elif bucket.time() == datetime.time(10, 0):
                # 当日第一桶：累计值从 0 开始，避免漏掉首分钟成交量。
                base_volume, base_amount = 0.0, 0.0
            else:
                # 盘中启动：只能从启动时刻开始累计。
                base_volume, base_amount = cum_volume, cum_amount
            self._last_cum_day[asset] = bucket.date()
            forming = {
                "date": bucket,
                "asset": asset,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.0,
                "amount": 0.0,
                "_base_volume": base_volume,
                "_base_amount": base_amount,
            }
            self._forming[asset] = forming
        forming["high"] = max(float(forming["high"]), price)
        forming["low"] = min(float(forming["low"]), price)
        forming["close"] = price
        forming["volume"] = max(0.0, cum_volume - float(forming["_base_volume"]))
        forming["amount"] = max(0.0, cum_amount - float(forming["_base_amount"]))
        self._last_cum[asset] = (cum_volume, cum_amount)

    def _complete(self, asset: str) -> None:
        forming = self._forming.pop(asset, None)
        if forming is None:
            return
        bar = {k: v for k, v in forming.items() if not k.startswith("_")}
        day = bar["date"].date()
        self._completed.setdefault(day, {}).setdefault(asset, []).append(bar)
        self._last_completed[asset] = bar["date"]

    def _finalize_due(self, now: datetime.datetime) -> None:
        """把已经收盘的桶落成完成 bar。

        A bar indexed by its close timestamp is complete at that timestamp.  The
        inclusive comparison is important for a scheduler that wakes exactly at
        10:00/10:30/etc.; using ``<`` would expose the previous forming bar to a
        30m strategy for one extra polling interval.
        """
        for asset, forming in list(self._forming.items()):
            if forming["date"] <= now:
                self._complete(asset)

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def completed(
        self,
        asset: str,
        end: datetime.datetime | None = None,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        """返回某标的已完成的当日/近几日内存 bar（按时间升序）。"""
        end = _naive(end or self._clock())
        with self._lock:
            self._finalize_due(end)
            rows: list[dict[str, Any]] = []
            for day in sorted(self._completed):
                rows.extend(self._completed[day].get(asset, []))
            forming = self._forming.get(asset)
            if forming is not None and forming["date"] <= end:
                rows.append({k: v for k, v in forming.items() if not k.startswith("_")})
            rows = [row for row in rows if row["date"] <= end]
        rows.sort(key=lambda row: row["date"])
        if count is not None:
            rows = rows[-int(count) :]
        return rows

    def forming(self, asset: str, now: datetime.datetime | None = None) -> dict[str, Any] | None:
        """返回某标的当前未完成桶（已收盘则返回 None）。"""
        now = _naive(now or self._clock())
        with self._lock:
            self._finalize_due(now)
            forming = self._forming.get(asset)
            if forming is None or forming["date"] <= now:
                return None
            return {k: v for k, v in forming.items() if not k.startswith("_")}

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------
    def clear_between(
        self, start: datetime.date, end: datetime.date, assets: Iterable[str] | None = None
    ) -> None:
        """Discard only the security/session ranges confirmed by durable historical data."""
        selected = set(assets) if assets is not None else None
        with self._lock:
            self._clear_completed_days(start, end, selected)
            self._clear_forming_bars(start, end, selected)
            self._clear_latest_markers(start, end, selected)

    def _clear_completed_days(
        self, start: datetime.date, end: datetime.date, selected: set[str] | None
    ) -> None:
        for day in list(self._completed):
            if not start <= day <= end:
                continue
            if selected is None:
                self._completed.pop(day, None)
            else:
                for asset in selected:
                    self._completed[day].pop(asset, None)

    def _clear_forming_bars(
        self, start: datetime.date, end: datetime.date, selected: set[str] | None
    ) -> None:
        for asset, forming in list(self._forming.items()):
            if (selected is None or asset in selected) and start <= forming["date"].date() <= end:
                self._forming.pop(asset, None)

    def _clear_latest_markers(
        self, start: datetime.date, end: datetime.date, selected: set[str] | None
    ) -> None:
        for asset, last in list(self._last_completed.items()):
            if (selected is None or asset in selected) and start <= last.date() <= end:
                self._last_completed.pop(asset, None)
                self._last_cum.pop(asset, None)
                self._last_cum_day.pop(asset, None)


#: 全局单例
minute_bar_aggregator = MinuteBarAggregator()

__all__ = ["MinuteBarAggregator", "minute_bar_aggregator"]
