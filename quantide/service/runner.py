import datetime
import inspect
import json
import threading
import uuid
from collections.abc import Iterable
from typing import Any, cast

import polars as pl
from loguru import logger

from quantide.config.settings import get_cheat_on_close_time
from quantide.core.enums import FrameType
from quantide.core.errors import RiskStrategyNotBacktestable
from quantide.core.order_execution import BROKER_ORDER_METHODS
from quantide.core.ports import ClockPort
from quantide.core.ports.broker import ExecutionResult
from quantide.core.runtime.clock_bridge import BacktestClockAdapter
from quantide.core.strategy import BaseStrategy, RiskStrategy, Strategy
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.minute_bars import minute_bars
from quantide.data.sqlite import db
from quantide.service.backtest_broker import BacktestBroker
from quantide.service.backtest_logs import record_backtest_log
from quantide.service.metrics import metrics
from quantide.service.risk_programs import (
    ALLOW_SAME_BAR_REPURCHASE_KEY,
    RISK_PROGRAMS_KEY,
    build_backtest_risk_overlay,
    normalize_risk_programs,
)


async def _await_overlay(result: Any) -> None:
    """Support both synchronous and asynchronous risk overlay adapters."""
    if inspect.isawaitable(result):
        await result


class _BacktestNextOpenBrokerProxy:
    """Queue host strategy orders until the following daily bar opens."""

    _ORDER_METHODS = BROKER_ORDER_METHODS

    def __init__(self, broker: BacktestBroker, mark_next_open: bool = False) -> None:
        self._broker = broker
        self._mark_next_open = mark_next_open
        self.pending: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, item: str) -> Any:
        return getattr(self._broker, item)

    def __getattribute__(self, item: str) -> Any:
        if item in object.__getattribute__(self, "_ORDER_METHODS"):

            async def queued(*args: Any, **kwargs: Any) -> ExecutionResult:
                object.__getattribute__(self, "pending").append((item, args, kwargs))
                return ExecutionResult.empty()

            return queued
        return object.__getattribute__(self, item)

    async def flush(self, order_time: datetime.datetime) -> None:
        pending = list(self.pending)
        self.pending.clear()
        for method_name, args, kwargs in pending:
            call_kwargs = dict(kwargs)
            call_kwargs["order_time"] = order_time
            # The minute feed uses this marker to distinguish a completed-bar
            # signal fill (close) from the following bar's open fill.
            if object.__getattribute__(self, "_mark_next_open"):
                call_kwargs["fill_timing"] = "next_open"
            await getattr(self._broker, method_name)(*args, **call_kwargs)


class BacktestRunner:
    """回测运行器，负责管理回测的生命周期和时间循环。"""

    def __init__(self, clock: ClockPort | None = None) -> None:
        """初始化回测运行器.

        Args:
            clock: 时钟端口实现。
        """
        self._clock = clock or BacktestClockAdapter()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Request interruption at the next replay boundary."""
        self._stop_event.set()

    @staticmethod
    def strategy_interval(strategy_cls: type[Strategy]) -> str:
        """Return the immutable interval declared by a strategy class."""
        declared = getattr(strategy_cls, "BAR_INTERVAL", None)
        if not isinstance(declared, str):
            declared = None
        if declared is None:
            declared = getattr(strategy_cls, "bar_interval", None)
            if not isinstance(declared, str):
                declared = None
        if declared is None:
            defaults = getattr(strategy_cls, "default_config", None)
            values = defaults() if callable(defaults) else {}
            declared = values.get("bar_interval", "1d") if isinstance(values, dict) else "1d"
        interval = str(declared).strip().lower()
        if interval not in {"1d", "30m"}:
            raise ValueError(f"策略声明了不支持的 bar_interval: {interval!r}")
        return interval

    @classmethod
    def validate_strategy_interval(
        cls,
        strategy_cls: type[Strategy],
        config: dict[str, Any] | None,
        frame_type: FrameType | str,
    ) -> str:
        expected = cls.strategy_interval(strategy_cls)
        supplied = (config or {}).get("bar_interval")
        if supplied is not None and str(supplied).strip().lower() != expected:
            raise ValueError(
                f"bar_interval override {supplied!r} conflicts with strategy interval {expected!r}"
            )
        actual = frame_type.value if isinstance(frame_type, FrameType) else str(frame_type).lower()
        if actual != expected:
            # A few legacy tests use a callable mock as the strategy factory
            # and exercise the pre-v0.2 1m runner.  There is no declaration to
            # validate in that path; real strategy classes are strict below.
            if not inspect.isclass(strategy_cls) and actual not in {"1d", "30m"}:
                return expected
            raise ValueError(f"回测周期 {actual!r} conflicts with strategy interval {expected!r}")
        return expected

    @staticmethod
    def _resolve_cheat_on_close(strategy_cls: type[BaseStrategy], config: dict[str, Any]) -> bool:
        """从 config / 类属性解析 cheat_on_close. config 优先."""
        if "cheat_on_close" in config:
            return bool(config["cheat_on_close"])
        return bool(getattr(strategy_cls, "cheat_on_close", False))

    @staticmethod
    def _resolve_cheat_on_close_time(cheat: bool) -> tuple[int, int]:
        """返回 (hour, minute) 触发时刻. cheat=True 走 settings.cheat_on_close_time, 否则 9:30."""
        if not cheat:
            return (9, 30)
        time_str = get_cheat_on_close_time()
        h, m = map(int, time_str.split(":"))
        return (h, m)

    @classmethod
    def _resolve_fill_timing(
        cls,
        strategy_cls: type[BaseStrategy],
        config: dict[str, Any],
    ) -> tuple[str, bool, tuple[int, int]]:
        """解析成交时点。

        支持：
        - ``next_open``（默认）：次日开盘成交；
        - ``auction_close``：14:57 用当日数据算信号，按收盘/竞价价成交；
        - ``close``：收盘价成交（沿用 cheat_on_close_time）。
        """
        raw = config.get("fill_timing", getattr(strategy_cls, "fill_timing", None))
        if raw is None:
            defaults = getattr(strategy_cls, "default_config", None)
            if callable(defaults):
                raw = defaults().get("fill_timing")
        fill_timing = str(raw).strip().lower() if raw is not None else ""
        if fill_timing in {"auction_close", "auction"}:
            return "auction_close", True, (14, 57)
        if fill_timing in {"close", "cheat_on_close"}:
            return "close", True, cls._resolve_cheat_on_close_time(True)
        if fill_timing in {"next_open", "open"}:
            return "next_open", False, (9, 30)
        # 未显式指定时保持旧行为：尊重 cheat_on_close 配置。
        cheat = cls._resolve_cheat_on_close(strategy_cls, config)
        return (
            ("close", True, cls._resolve_cheat_on_close_time(True))
            if cheat
            else ("next_open", False, (9, 30))
        )

    def _align_backtest_dates(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        frame_type: FrameType = FrameType.DAY,
    ) -> tuple[datetime.date, datetime.date]:
        """对齐回测起止日期到交易日。

        Args:
            start_date: 回测开始日期
            end_date: 回测结束日期

        Returns:
            tuple[datetime.date, datetime.date]: 对齐后的起止日期
        """
        start_date = calendar.ceiling(start_date, FrameType.DAY)
        end_date = calendar.floor(end_date, FrameType.DAY)
        if start_date > end_date:
            raise ValueError(f"回测开始日期 {start_date} 不能晚于结束日期 {end_date}")
        if frame_type == FrameType.MIN30:
            # The 30m feed has its own coverage and must not silently inherit a
            # shorter daily range (or turn into a daily backtest).
            return start_date, end_date
        return start_date, self._clamp_end_date_to_market_data(end_date, start_date)

    @staticmethod
    def _clamp_end_date_to_market_data(
        end_date: datetime.date,
        start_date: datetime.date,
    ) -> datetime.date:
        """把回测结束日期收敛到行情数据覆盖的最后交易日。

        行情数据滞后时，最后一根 bar 没有行情，卖出/清仓会因为拿不到
        撮合价而失败，因此这里提前收敛，避免回测在收尾阶段报错。

        Args:
            end_date: 对齐后的回测结束日期。
            start_date: 对齐后的回测开始日期。

        Returns:
            datetime.date: 收敛后的结束日期。
        """
        # Fixture/custom feeds may expose only the range-read API.  Without an
        # explicit end marker there is no safe clamp to apply, so retain the
        # caller's validated date range and let the feed drive availability.
        last_data_date = getattr(daily_bars, "end", None)
        if not isinstance(last_data_date, datetime.date) or end_date <= last_data_date:
            return end_date
        clamped = calendar.floor(last_data_date, FrameType.DAY)
        if clamped < start_date:
            raise ValueError(f"行情数据仅覆盖到 {last_data_date}，无法回测 {start_date} 之后的区间")
        logger.warning(
            "回测结束日期 {} 超出行情数据范围，已收敛到 {}（请更新行情数据后重跑）",
            end_date,
            clamped,
        )
        return clamped

    def _init_backtest(
        self,
        strategy_cls: type[BaseStrategy],
        config: dict[str, Any],
        start_date: datetime.date,
        end_date: datetime.date,
        frame_type: FrameType,
        initial_cash: float,
        portfolio_id: str | None,
        db_path: str | None,
        save_logs: bool,
    ) -> tuple[str, BacktestBroker, BaseStrategy]:
        """初始化回测环境，包括 Broker、Strategy 和数据库。

        Args:
            strategy_cls: 策略类
            config: 策略配置
            start_date: 回测开始日期
            end_date: 回测结束日期
            frame_type: 回测周期类型
            initial_cash: 初始资金
            portfolio_id: 组合 ID，如果为 None 则自动生成
            db_path: 数据库路径，如果为 None 则使用默认路径
            save_logs: 是否同步写入回测日志文件。

        Returns:
            tuple: (portfolio_id, broker, strategy)
        """
        if portfolio_id is None:
            portfolio_id = uuid.uuid4().hex

        # Initialize DB if provided (e.g. for multi-process isolation with :memory:)
        if db_path:
            db.init(db_path)

        # 1. Init Broker
        risk_overlay = None
        if RISK_PROGRAMS_KEY in config:
            risk_overlay = build_backtest_risk_overlay(strategy_cls, config, frame_type)
        broker = BacktestBroker(
            bt_start=start_date,
            bt_end=end_date,
            portfolio_id=portfolio_id,
            data_feed=daily_bars,  # type: ignore
            minute_bars=minute_bars if frame_type == FrameType.MIN30 else None,
            principal=initial_cash,
            commission=float(config.get("commission", 1e-4)),
            stamp_duty=float(config.get("stamp_duty", 5e-4)),
            min_commission=float(config.get("min_commission", 5.0)),
            transfer_fee=float(config.get("transfer_fee", 1e-5)),
            match_level="day" if frame_type == FrameType.DAY else "minute",
            portfolio_name=strategy_cls.__name__,
            desc=json.dumps({"config": dict(config or {})}, ensure_ascii=False),
            save_logs=save_logs,
            risk_overlay=risk_overlay,
            auction_epsilon=float(config.get("auction_epsilon", 0.001)),
            allow_same_bar_repurchase=bool(config.get(ALLOW_SAME_BAR_REPURCHASE_KEY, True)),
        )

        # Use patched logger
        self.logger = logger.bind(runner="BacktestRunner", portfolio_id=portfolio_id)
        self.logger.info(f"Starting backtest for {strategy_cls.__name__} ({portfolio_id})")
        record_backtest_log(
            portfolio_id=portfolio_id,
            level="INFO",
            source="runner",
            message=(
                f"开始回测：策略={strategy_cls.__name__}，区间={start_date}~{end_date}，"
                f"周期={frame_type.value}，初始资金={initial_cash:.2f}"
            ),
            dt=calendar.replace_time(start_date, 9, 0),
            extra={"interval": frame_type.value, "initial_cash": initial_cash},
            save_to_file=save_logs,
        )

        # 2. Init Strategy
        strategy = strategy_cls(broker, config)
        strategy.interval = frame_type.value
        # Risk overlays need the same immutable interval as the host strategy;
        # they must not infer 30m from the broker's daily accounting feed.
        broker.interval = frame_type.value

        return portfolio_id, broker, strategy

    async def _handle_day_switch(
        self,
        strategy: BaseStrategy,
        broker: BacktestBroker,
        current_date: datetime.date,
        last_trade_day: datetime.date | None,
    ) -> datetime.date:
        """处理日间切换逻辑（收盘和开盘）。

        Args:
            strategy: 策略实例
            broker: Broker 实例
            current_date: 当前交易日
            last_trade_day: 上一个交易日

        Returns:
            datetime.date: 更新后的 last_trade_day (即 current_date)
        """
        if last_trade_day is None or current_date != last_trade_day:
            # Close previous day if exists
            if last_trade_day is not None:
                close_tm = calendar.replace_time(last_trade_day, 15, 30)
                self._clock.set_now(close_tm)
                broker.set_clock(close_tm)
                strategy._current_time = close_tm
                await strategy.on_day_close(close_tm)

            # Open new day
            open_tm = calendar.replace_time(current_date, 9, 30)
            self._clock.set_now(open_tm)
            broker.set_clock(open_tm)
            strategy._current_time = open_tm
            await strategy.on_day_open(open_tm)

            return current_date
        return last_trade_day

    @staticmethod
    def _benchmark_returns(
        benchmark: Any,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> pl.DataFrame | None:
        """读取指数日线并计算基准日收益率；不可用时返回 None。"""
        code = str(benchmark).strip() if benchmark else ""
        if not code:
            return None
        try:
            from quantide.data import get_index_bars_store

            store = get_index_bars_store()
            frame = store.get([code], start_date, end_date)
            if not isinstance(frame, pl.DataFrame) or frame.is_empty():
                return None
            frame = frame.sort("date")
            dates = frame["date"].to_list()
            if not dates or dates[0] > start_date or dates[-1] < end_date:
                return None
            returns = frame.select(
                pl.col("date").alias("dt"),
                (pl.col("close") / pl.col("close").shift(1) - 1).alias("returns"),
            ).drop_nulls()
            return returns
        except Exception:  # pragma: no cover - 缺数据时静默跳过基准
            return None

    def _resolve_day_signal_date(
        self,
        current_date: datetime.date,
        bar_tm: datetime.datetime,
    ) -> datetime.date:
        """返回日线策略在当前时间点可见的最新完整交易日。

        日线回测的交易信号在开盘时生成，因此此时只能使用上一交易日
        已经完整收盘的数据，避免“看到当天收盘价后又按当天收盘价成交”的前视偏差。

        Args:
            current_date: 当前交易日。
            bar_tm: 当前 bar 的触发时间。

        Returns:
            可用于生成信号的最近完整交易日。
        """
        if bar_tm.time() <= datetime.time(9, 30):
            return calendar.day_shift(current_date, -1)
        return current_date

    def _get_bar_quote(
        self,
        broker: BacktestBroker,
        current_date: datetime.date,
        bar_tm: datetime.datetime,
        config: dict[str, Any],
        frame_type: FrameType,
    ) -> dict[str, Any]:
        """获取当前 Bar 的行情快照。

        Args:
            broker: Broker 实例
            current_date: 当前日期
            bar_tm: 当前 Bar 时间
            config: 策略配置
            frame_type: 当前 Bar 的周期类型

        Returns:
            Dict[str, Any]: 行情快照字典
        """
        quote = {}
        if frame_type == FrameType.DAY:
            universe = config.get("universe", [])
            assets = list(set(list(broker.positions.keys()) + universe))

            if assets:
                quote_date = self._resolve_day_signal_date(current_date, bar_tm)
                df = cast(
                    pl.DataFrame, daily_bars.get_bars_in_range(quote_date, quote_date, assets)
                )
                if not df.is_empty():
                    for row in df.iter_rows(named=True):
                        quote[row["asset"]] = {
                            "lastPrice": row["close"],
                            "volume": row["volume"],
                        }
        else:
            # TODO: Implement minute bar quote fetching
            pass
        return quote

    async def run(
        self,
        strategy_cls: type[BaseStrategy],
        config: dict[str, Any],
        start_date: datetime.date,
        end_date: datetime.date,
        frame_type: FrameType = FrameType.DAY,
        initial_cash: float = 1_000_000,
        portfolio_id: str | None = None,
        db_path: str | None = None,
        save_logs: bool = False,
    ) -> dict[str, Any]:
        """Run the strategy through setup, clock replay, closing and metrics calculation."""
        config = self._normalized_run_config(strategy_cls, config, frame_type)
        start_date, end_date = self._align_backtest_dates(start_date, end_date, frame_type)
        portfolio_id, broker, strategy = self._init_backtest(
            strategy_cls,
            config,
            start_date,
            end_date,
            frame_type,
            initial_cash,
            portfolio_id,
            db_path,
            save_logs,
        )
        try:
            await strategy.init()
            await strategy.on_start()
            await self._run_clock_frames(
                strategy, broker, strategy_cls, config, start_date, end_date, frame_type
            )
            await broker.stop_backtest()
        except Exception as exc:
            self.logger.exception("Backtest failed: {}", exc)
            self._record_run_log(
                portfolio_id, strategy, broker, "ERROR", f"回测失败：{exc}", save_logs
            )
            raise
        finally:
            await strategy.on_stop()
        self.logger.info(f"Backtest finished: {portfolio_id}")
        self._record_run_log(
            portfolio_id,
            strategy,
            broker,
            "INFO",
            f"回测结束：portfolio_id={portfolio_id}",
            save_logs,
        )
        return self._run_metrics(portfolio_id, config, start_date, end_date)

    def _normalized_run_config(
        self, strategy_cls: type[BaseStrategy], config: dict[str, Any], frame_type: FrameType
    ) -> dict[str, Any]:
        if inspect.isclass(strategy_cls) and issubclass(strategy_cls, RiskStrategy):
            raise RiskStrategyNotBacktestable(getattr(strategy_cls, "__name__", ""))
        self.validate_strategy_interval(strategy_cls, config, frame_type)
        if RISK_PROGRAMS_KEY in config:
            config = dict(config)
            config[RISK_PROGRAMS_KEY] = normalize_risk_programs(
                config.get(RISK_PROGRAMS_KEY),
                host_strategy_cls=strategy_cls,
                frame_type=frame_type,
            )
            config.setdefault(ALLOW_SAME_BAR_REPURCHASE_KEY, True)
        return config

    def _iter_backtest_frames(
        self, start_date: datetime.date, end_date: datetime.date, frame_type: FrameType
    ) -> Iterable[datetime.date | datetime.datetime]:
        if frame_type in {
            FrameType.MIN1,
            FrameType.MIN5,
            FrameType.MIN15,
            FrameType.MIN30,
            FrameType.MIN60,
        }:
            return self._clock.iter_frames(
                calendar.first_min_frame(start_date, frame_type),
                calendar.last_min_frame(end_date, frame_type),
                frame_type,
            )
        return self._clock.iter_frames(start_date, end_date, frame_type)

    def _next_open_settings(
        self,
        strategy_cls: type[BaseStrategy],
        config: dict[str, Any],
        frame_type: FrameType,
        broker: BacktestBroker,
    ) -> tuple[_BacktestNextOpenBrokerProxy | None, tuple[int, int]]:
        fill_timing, _, cheat_tm = self._resolve_fill_timing(strategy_cls, config)
        declared = getattr(strategy_cls, "fill_timing", None)
        if not isinstance(declared, str):
            defaults = getattr(strategy_cls, "default_config", None)
            if callable(defaults):
                declared = defaults().get("fill_timing")
        explicit = str(config.get("fill_timing", "")).lower() in {"next_open", "open"} or (
            isinstance(declared, str) and declared.lower() in {"next_open", "open"}
        )
        enabled = (
            frame_type in {FrameType.DAY, FrameType.MIN30}
            and fill_timing == "next_open"
            and explicit
        )
        proxy = (
            _BacktestNextOpenBrokerProxy(broker, mark_next_open=frame_type == FrameType.MIN30)
            if enabled
            else None
        )
        self.logger.info(f"回测成交时点: {fill_timing}")
        return proxy, cheat_tm

    async def _run_clock_frames(
        self,
        strategy: BaseStrategy,
        broker: BacktestBroker,
        strategy_cls: type[BaseStrategy],
        config: dict[str, Any],
        start_date: datetime.date,
        end_date: datetime.date,
        frame_type: FrameType,
    ) -> None:
        proxy, cheat_tm = self._next_open_settings(strategy_cls, config, frame_type, broker)
        strategy.interval = frame_type.value
        last_trade_day = None
        for tm in self._iter_backtest_frames(start_date, end_date, frame_type):
            if self._stop_event.is_set():
                raise InterruptedError("服务停止，回测被中断；已完成的交易记录保留")
            current_date = tm.date() if isinstance(tm, datetime.datetime) else tm
            bar_tm = (
                tm if isinstance(tm, datetime.datetime) else calendar.replace_time(tm, *cheat_tm)
            )
            last_trade_day = await self._handle_day_switch(
                strategy, broker, current_date, last_trade_day
            )
            broker.begin_risk_overlay_cycle()
            await self._run_strategy_bar(
                strategy, broker, current_date, bar_tm, config, frame_type, proxy
            )
        if last_trade_day is not None:
            close_tm = calendar.replace_time(last_trade_day, 15, 30)
            self._set_strategy_time(strategy, broker, close_tm)
            await strategy.on_day_close(close_tm)

    def _set_strategy_time(
        self, strategy: BaseStrategy, broker: BacktestBroker, moment: datetime.datetime
    ) -> None:
        self._clock.set_now(moment)
        broker.set_clock(moment)
        strategy._current_time = moment

    async def _run_strategy_bar(
        self,
        strategy: BaseStrategy,
        broker: BacktestBroker,
        current_date: datetime.date,
        bar_tm: datetime.datetime,
        config: dict[str, Any],
        frame_type: FrameType,
        proxy: _BacktestNextOpenBrokerProxy | None,
    ) -> None:
        if proxy is not None:
            await proxy.flush(bar_tm)
            if frame_type == FrameType.DAY:
                bar_tm = calendar.replace_time(current_date, 15, 0)
        self._set_strategy_time(strategy, broker, bar_tm)
        self._get_bar_quote(broker, current_date, bar_tm, config, frame_type)
        overlay = frame_type in {FrameType.DAY, FrameType.MIN30}
        if overlay:
            await _await_overlay(broker.run_risk_overlay(bar_tm))
        if proxy is None:
            await strategy.on_bar(bar_tm)
        else:
            original_broker = strategy.broker
            strategy.broker = proxy
            try:
                await strategy.on_bar(bar_tm)
            finally:
                strategy.broker = original_broker
        if overlay:
            broker.sync_risk_overlay(bar_tm)
            await _await_overlay(broker.run_risk_overlay_intraday(bar_tm))

    def _record_run_log(
        self,
        portfolio_id: str,
        strategy: BaseStrategy,
        broker: BacktestBroker,
        level: str,
        message: str,
        save_logs: bool,
    ) -> None:
        record_backtest_log(
            portfolio_id=portfolio_id,
            level=level,
            source="runner",
            message=message,
            dt=strategy._current_time or broker._clock,
            save_to_file=save_logs,
        )

    def _run_metrics(
        self,
        portfolio_id: str,
        config: dict[str, Any],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, Any]:
        baseline = self._benchmark_returns(
            config.get("benchmark", "000300.SH"), start_date, end_date
        )
        try:
            stats = metrics(portfolio_id, baseline_returns=baseline, start=start_date, end=end_date)
        except ValueError as exc:
            self.logger.warning(f"基准对齐失败，跳过超额指标: {exc}")
            stats = metrics(portfolio_id, start=start_date, end=end_date)
        return {
            "portfolio_id": portfolio_id,
            "metrics": stats.to_dict() if stats is not None else {},
        }
