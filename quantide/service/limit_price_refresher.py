"""当日涨跌停限价刷新（Tushare 早晨发布 + 启动时）。

Tushare 每个交易日早晨发布当日 ``stk_limit``。本服务：

- 启动时立即刷新一次（进程中途启动也能拿到当日限价）；
- 09:00 刷新；若未成功，09:20 再补拉一次；
- 结果写入 :class:`LimitPriceStore`（按日持久化）并广播
  ``stock_limit``，供 Paper 撮合与 30 分钟线读取使用；
- 与实时行情发布者推送的涨跌停构成双链路，互为主备。

不做重试风暴：09:20 只补拉一次；非交易日直接跳过。
"""

from __future__ import annotations

import datetime
import threading
from typing import Any

import polars as pl
from loguru import logger

from quantide.core.enums import Topics
from quantide.core.market_time import market_now
from quantide.core.message import msg_hub
from quantide.core.scheduler import scheduler
from quantide.service.scheduled_jobs import remove_owned_jobs

#: 领取当日限价的任务 id
_JOB_0900 = "limit_price_refresh_0900"
_JOB_0920 = "limit_price_refresh_0920"


def _default_fetcher() -> Any:
    from quantide.data.fetchers.registry import get_data_fetcher

    return get_data_fetcher()


def _default_store() -> Any:
    from quantide.data import get_limit_price_store

    return get_limit_price_store()


class LimitPriceRefresher:
    """把 Tushare 当日涨跌停写入本地并推送到行情总线。"""

    def __init__(
        self,
        fetcher_factory: Any | None = None,
        store_factory: Any | None = None,
        calendar: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self._fetcher_factory = fetcher_factory or _default_fetcher
        self._store_factory = store_factory or _default_store
        self._clock = clock or market_now
        if calendar is None:
            from quantide.data.models.calendar import calendar as default_calendar

            calendar = default_calendar
        self._calendar = calendar
        self._lock = threading.RLock()
        self._scheduled = False
        self._last_success: datetime.date | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Remove this service's registrations before a subsequent lifespan."""
        remove_owned_jobs(self, scheduler, ("limit_price_refresh_0900", "limit_price_refresh_0920"))

    def start(self) -> None:
        """注册定时任务并立即刷新一次（幂等）。"""
        with self._lock:
            if self._scheduled:
                return
            scheduler.add_job(
                self.refresh,
                "cron",
                hour=9,
                minute=0,
                id=_JOB_0900,
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=None,
                name="limit_price.refresh.0900",
            )
            scheduler.add_job(
                self._refresh_if_needed,
                "cron",
                hour=9,
                minute=20,
                id=_JOB_0920,
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=None,
                name="limit_price.refresh.0920",
            )
            self._scheduled = True
        self.refresh()

    def _refresh_if_needed(self) -> None:
        today = self._clock().date()
        if self._last_success != today:
            self.refresh()

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------
    def refresh(self, dt: datetime.date | None = None) -> bool:
        """拉取 ``dt`` 当日涨跌停并写入存储/广播。

        Returns:
            bool: 是否拿到并处理了数据。
        """
        dt = dt or self._clock().date()
        if not self._is_trade_day(dt):
            logger.info("{} 非交易日，跳过当日涨跌停刷新", dt)
            return False
        with self._lock:
            try:
                frame, errors = self._fetcher_factory().fetch_limit_price(dt)
            except Exception as exc:
                logger.warning("当日涨跌停拉取失败 {}: {}", dt, exc)
                return False
            if errors:
                logger.warning("当日涨跌停拉取返回错误 {}: {}", dt, errors[:3])
            if frame is None or len(frame) == 0:
                logger.warning("当日涨跌停为空（{}），等待 09:20 补拉", dt)
                return False
            normalized = _normalize_limits(frame, dt)
            if normalized.is_empty():
                logger.warning("当日涨跌停没有有效记录（{}）", dt)
                return False
            try:
                self._store_factory().append_data(normalized)
            except Exception as exc:
                logger.warning("当日涨跌停写入失败 {}: {}", dt, exc)
            self._publish(normalized)
            self._last_success = dt
            logger.info("当日涨跌停已更新：{}，{} 只", dt, normalized.height)
            return True

    def _is_trade_day(self, dt: datetime.date) -> bool:
        try:
            return bool(self._calendar.is_trade_day(dt))
        except Exception:  # pragma: no cover - 日历未加载时按交易日处理
            return True

    @staticmethod
    def _publish(frame: pl.DataFrame) -> None:
        payload: dict[str, dict[str, float]] = {}
        for row in frame.iter_rows(named=True):
            up = float(row.get("up_limit") or 0.0)
            down = float(row.get("down_limit") or 0.0)
            payload[str(row["asset"])] = {
                "up": up,
                "down": down,
                "up_limit": up,
                "down_limit": down,
            }
        if payload:
            msg_hub.publish(Topics.STOCK_LIMIT.value, payload)


def _normalize_limits(frame: Any, dt: datetime.date) -> pl.DataFrame:
    """统一为 date/asset/up_limit/down_limit 并去重。"""
    out = frame if isinstance(frame, pl.DataFrame) else pl.from_pandas(frame)
    if "asset" not in out.columns and "ts_code" in out.columns:
        out = out.rename({"ts_code": "asset"})
    if "date" not in out.columns:
        out = out.with_columns(pl.lit(dt).alias("date"))
    for col in ("up_limit", "down_limit"):
        if col not in out.columns:
            out = out.with_columns(pl.lit(0.0).alias(col))
    out = (
        out.select(["date", "asset", "up_limit", "down_limit"])
        .with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("asset").cast(pl.Utf8),
            pl.col("up_limit").cast(pl.Float64).fill_null(0.0),
            pl.col("down_limit").cast(pl.Float64).fill_null(0.0),
        )
        .unique(subset=["date", "asset"], keep="last")
        .sort(["date", "asset"])
    )
    return out


#: 全局单例
limit_price_refresher = LimitPriceRefresher()

__all__ = ["LimitPriceRefresher", "limit_price_refresher"]
