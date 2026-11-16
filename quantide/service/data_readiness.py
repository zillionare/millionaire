"""数据就绪 / 行情健康检查。

在关键时间点检查当日涨跌停、上一交易日（或当日收盘后）复权/ST/涨跌停数据、
以及盘中实时行情是否持续到达。异常写入系统级风险事件：

- ``blocked=True`` → header 告警计数 + 风险事件中心；
- 恢复后写入 ``blocked=False`` 的信息事件，不再占用告警计数。
"""

from __future__ import annotations

import datetime
import threading
from typing import Any

from loguru import logger

from quantide.core.market_time import market_now
from quantide.core.scheduler import scheduler
from quantide.service.scheduled_jobs import remove_owned_jobs

_QUOTE_STALE_SECONDS = 60.0
_LIMIT_COVERAGE_THRESHOLD = 0.80
_DAILY_LIMIT_COVERAGE_THRESHOLD = 0.80
_ADJUST_COVERAGE_THRESHOLD = 0.90


def _default_recorder(**kwargs: Any) -> None:
    from quantide.service.strategy_runtime import strategy_runtime_manager

    strategy_runtime_manager.record_system_event(**kwargs)


class DataReadinessMonitor:
    """检查数据与实时行情，并把状态变化写入风险事件。"""

    def __init__(
        self,
        *,
        daily_store: Any | None = None,
        limit_store_factory: Any | None = None,
        stocks: Any | None = None,
        calendar: Any | None = None,
        quote_monitor: Any | None = None,
        clock: Any | None = None,
        recorder: Any | None = None,
    ) -> None:
        self._daily = daily_store
        self._limit_store_factory = limit_store_factory
        self._stocks = stocks
        self._calendar = calendar
        self._quotes = quote_monitor
        self._clock = clock or market_now
        self._record = recorder or _default_recorder
        self._states: dict[str, bool] = {}
        self._lock = threading.RLock()
        self._scheduled = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Remove this service's registrations before a subsequent lifespan."""
        remove_owned_jobs(
            self,
            scheduler,
            ("data_readiness_morning", "data_readiness_eod", "data_readiness_quotes"),
        )

    def start(self) -> None:
        """注册定时检查；启动时立即检查一次日线/限价。"""
        with self._lock:
            if self._scheduled:
                return
            scheduler.add_job(
                self.check_morning,
                "cron",
                hour="9,10,11,13,14",
                minute="25,55",
                id="data_readiness_morning",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=None,
                name="data_readiness.morning",
            )
            scheduler.add_job(
                self.check_end_of_day,
                "cron",
                hour=18,
                minute=30,
                id="data_readiness_eod",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=None,
                name="data_readiness.eod",
            )
            scheduler.add_job(
                self.check_quotes,
                "cron",
                hour="9,10,11,13,14,15",
                minute="*",
                id="data_readiness_quotes",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=None,
                name="data_readiness.quotes",
            )
            self._scheduled = True
        self._load_existing_alerts()
        self.check_morning()
        self.check_end_of_day()

    def _load_existing_alerts(self) -> None:
        """重启后恢复未解决的数据告警状态，避免重复告警或无法恢复。"""
        try:
            from quantide.service.strategy_runtime import strategy_runtime_manager

            for event in strategy_runtime_manager.list_risk_events(limit=100):
                target_id = str(event.get("target_id") or "")
                if event.get("blocked") and target_id.startswith("data:"):
                    self._states[target_id.removeprefix("data:")] = False
        except Exception:  # pragma: no cover - 运行时未就绪
            pass

    # ------------------------------------------------------------------
    # 检查项
    # ------------------------------------------------------------------
    def check_morning(self, now: datetime.datetime | None = None) -> None:
        now = now or self._clock()
        calendar = self._calendar_obj()
        try:
            if not calendar.is_trade_day(now):
                return
            today = now.date()
            prev = calendar.day_shift(today, -1)
        except Exception as exc:  # pragma: no cover - 日历未就绪
            logger.warning("数据就绪检查无法读取交易日历: {}", exc)
            return
        self._check_daily_freshness(prev, label="上一交易日")
        self._check_daily_aux(prev)
        self._check_limits(today)

    def check_end_of_day(self, now: datetime.datetime | None = None) -> None:
        now = now or self._clock()
        if now.time() < datetime.time(18, 30):
            return
        calendar = self._calendar_obj()
        try:
            if not calendar.is_trade_day(now):
                return
        except Exception:  # pragma: no cover
            return
        today = now.date()
        self._check_daily_freshness(today, label="当日")
        self._check_daily_aux(today)
        self._check_limits(today)

    def is_daily_ready(
        self,
        now: datetime.datetime,
        *,
        day: datetime.date | None = None,
    ) -> bool:
        """Return whether a completed daily bar is persisted and usable.

        A current-day bar is accepted only after the exchange session has
        ended, and the persisted store is queried again for that exact date.
        The market close boundary is used; there is no wall-clock grace
        period such as a fixed 15:05 trigger.
        """
        expected = day or now.date()
        calendar = self._calendar_obj()
        try:
            # This gate is used for same-day next-open decisions.  A previous
            # day's persisted bar may be useful for other health checks, but
            # it must never be mistaken for today's post-persistence event.
            if expected != now.date():
                return False
            if not calendar.is_trade_day(expected):
                return False
            if now.time() < datetime.time(15, 0):
                return False
            end = self._daily_obj().end
            if end != expected:
                return False
            frame = self._daily_obj().get_bars_in_range(
                expected,
                expected,
                assets=None,
                adjust=None,
                eager_mode=True,
            )
            if frame is None or frame.is_empty():
                return False
            required = {"date", "asset", "open", "high", "low", "close", "volume"}
            if not required.issubset(set(frame.columns)):
                return False
            selected = frame.select(sorted(required))
            return bool(selected.null_count().row(0) == (0,) * len(required))
        except Exception:
            return False

    def check_quotes(self, now: datetime.datetime | None = None) -> None:
        now = now or self._clock()
        if not self._in_session(now):
            return
        # 开盘/午后第一分钟给发布者一个启动宽限，避免 13:00:00 的
        # 定时检查在首笔行情到达前误报“行情中断”。
        tm = now.time()
        if datetime.time(9, 30) <= tm < datetime.time(9, 31) or (
            datetime.time(13, 0) <= tm < datetime.time(13, 1)
        ):
            return
        status = self._quotes_obj().status()
        last = status.get("last_received_at")
        if not status.get("started"):
            self._set_state(
                "quotes",
                False,
                title="实时行情监视器未启动",
                message="行情监视器未订阅 quotes.all，系统可能收不到盘中行情。",
            )
            return
        if not isinstance(last, datetime.datetime):
            age = None
            stale = True
        else:
            age = max(0.0, (now - last).total_seconds())
            stale = age > _QUOTE_STALE_SECONDS
        if stale:
            detail = "尚未收到任何行情" if age is None else f"已 {age:.0f}s 未收到行情"
            self._set_state(
                "quotes",
                False,
                title="实时行情中断",
                message=f"{detail}（阈值 {_QUOTE_STALE_SECONDS:.0f}s）。",
            )
        else:
            self._set_state(
                "quotes",
                True,
                title="实时行情恢复",
                message=f"行情已恢复，最近一次推送延迟 {age:.0f}s。",
            )

    # ------------------------------------------------------------------
    # 内部检查
    # ------------------------------------------------------------------
    def _check_daily_freshness(self, expected: datetime.date, *, label: str) -> None:
        try:
            end = self._daily_obj().end
        except Exception as exc:  # pragma: no cover
            self._set_state(
                "daily_freshness",
                False,
                title="日线数据不可用",
                message=f"无法读取日线存储：{exc}",
            )
            return
        ok = end is not None and end >= expected
        if ok:
            message = f"日线已更新到 {end}（{label}要求 {expected}）。"
        else:
            message = f"日线最新日期为 {end or '无数据'}，{label}要求至少 {expected}。"
        self._set_state(
            "daily_freshness",
            ok,
            title="日线数据未更新",
            message=message,
        )

    def _check_daily_aux(self, day: datetime.date) -> None:
        try:
            frame = self._daily_obj().get_bars_in_range(
                day, day, assets=None, adjust=None, eager_mode=True
            )
        except Exception as exc:  # pragma: no cover
            self._set_state(
                "daily_aux",
                False,
                title="日线辅助数据不可用",
                message=f"{day} 复权/涨跌停数据读取失败：{exc}",
            )
            return
        if frame is None or frame.is_empty():
            self._set_state(
                "daily_aux",
                False,
                title="日线辅助数据缺失",
                message=f"缺少 {day} 的日线数据，无法提供复权因子/ST/涨跌停。",
            )
            return
        total = max(1, frame.height)
        if "adjust" in frame.columns:
            adjust_cov = frame["adjust"].is_not_null().sum() / total
            # 全为 1.0 通常意味着复权因子抓取失败（Tushare 会 fillna(1.0)）。
            adjust_ratio = (frame["adjust"] != 1.0).sum() / total
        else:
            adjust_cov = 0.0
            adjust_ratio = 0.0
        if {"up_limit", "down_limit"}.issubset(frame.columns):
            limit_cov = ((frame["up_limit"] > 0) & (frame["down_limit"] > 0)).sum() / total
        else:
            limit_cov = 0.0
        ok = (
            adjust_cov >= _ADJUST_COVERAGE_THRESHOLD
            and adjust_ratio >= 0.50
            and limit_cov >= _DAILY_LIMIT_COVERAGE_THRESHOLD
        )
        message = (
            f"{day} 共 {total} 行：复权因子覆盖 {adjust_cov * 100:.1f}%，"
            f"有效因子 {adjust_ratio * 100:.1f}%，涨跌停覆盖 {limit_cov * 100:.1f}%。"
        )
        self._set_state(
            "daily_aux",
            ok,
            title="日线复权/涨跌停数据不完整",
            message=message,
        )

    def _check_limits(self, day: datetime.date) -> None:
        try:
            limits = self._limit_store().limits_map(day)
        except Exception as exc:  # pragma: no cover
            self._set_state(
                "limit_today",
                False,
                title="当日涨跌停不可用",
                message=f"无法读取 {day} 涨跌停存储：{exc}",
            )
            return
        count = len(limits)
        expected = int(getattr(self._stocks_obj(), "size", 0) or 0)
        coverage = count / expected if expected else (1.0 if count else 0.0)
        ok = coverage >= _LIMIT_COVERAGE_THRESHOLD
        message = f"{day} 已入库 {count}/{expected or '?'} 只（{coverage * 100:.1f}%）。"
        self._set_state(
            "limit_today",
            ok,
            title="当日涨跌停缺失",
            message=message,
        )

    # ------------------------------------------------------------------
    # 状态与依赖
    # ------------------------------------------------------------------
    def _set_state(
        self,
        key: str,
        ok: bool,
        *,
        title: str,
        message: str,
        severity: str = "critical",
    ) -> None:
        previous = self._states.get(key)
        if ok:
            if previous is False:
                self._record(
                    title=f"数据恢复：{title}",
                    message=message,
                    severity="info",
                    blocked=False,
                    target_id=f"data:{key}",
                )
            self._states[key] = True
            return
        if previous is not False:
            self._record(
                title=title,
                message=message,
                severity=severity,
                blocked=True,
                target_id=f"data:{key}",
            )
        self._states[key] = False

    def _in_session(self, now: datetime.datetime) -> bool:
        try:
            if not self._calendar_obj().is_trade_day(now):
                return False
        except Exception:  # pragma: no cover
            return False
        tm = now.time()
        return datetime.time(9, 30) <= tm <= datetime.time(11, 30) or (
            datetime.time(13, 0) <= tm <= datetime.time(15, 0)
        )

    def _calendar_obj(self) -> Any:
        if self._calendar is not None:
            return self._calendar
        from quantide.data.models.calendar import calendar

        return calendar

    def _daily_obj(self) -> Any:
        if self._daily is not None:
            return self._daily
        from quantide.data.models.daily_bars import daily_bars

        return daily_bars

    def _limit_store(self) -> Any:
        if self._limit_store_factory is not None:
            return self._limit_store_factory()
        from quantide.data import get_limit_price_store

        return get_limit_price_store()

    def _stocks_obj(self) -> Any:
        if self._stocks is not None:
            return self._stocks
        from quantide.data.models.stocks import stock_list

        return stock_list

    def _quotes_obj(self) -> Any:
        if self._quotes is not None:
            return self._quotes
        from quantide.service.quote_monitor import quote_monitor

        return quote_monitor


#: 全局单例
data_readiness_monitor = DataReadinessMonitor()

__all__ = ["DataReadinessMonitor", "data_readiness_monitor"]
