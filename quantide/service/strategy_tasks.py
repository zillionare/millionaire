"""每个策略独立的任务：dry-run 影子、实际快照、模型重训。"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from quantide.core.scheduler import scheduler
from quantide.data.models.calendar import calendar
from quantide.service.model_store import model_store
from quantide.service.shadow_broker import ShadowBroker
from quantide.service.strategy_tracking import tracking_store

if TYPE_CHECKING:
    from quantide.service.strategy_runtime import StrategyRuntime


def _replay_previous_shadow_session(
    self: StrategyTaskManager,
    run: dict[str, Any],
    last: str,
    previous: datetime.date,
    runtime: StrategyRuntime,
    runtime_id: str,
) -> None:
    """Replay a missed previous session before evaluating the morning strategy."""
    if run.get("dry_run_enabled", True) and last < previous.isoformat():
        shadow = None
        if self._can_replay(runtime, previous):
            shadow = self._run_shadow(runtime, previous)
        if shadow is None:
            gaps = list(run.get("gap_dates") or [])
            if previous.isoformat() not in gaps:
                gaps.append(previous.isoformat())
            tracking_store.update_run(runtime_id, gap_dates=gaps)


_EOD_HOUR = 18
_EOD_MINUTE = 45
_MORNING_HOUR = 8
_MORNING_MINUTE = 30
_SUPPORTED_FILL_TIMINGS = {
    "auction_close",
    "close",
    "auction",
    "cheat_on_close",
    "next_open",
    "open",
}


def _job_prefix(runtime_id: str) -> str:
    return f"strategy:{runtime_id}"


def _to_date(value: object) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return None


def _model_hash(strategy: object) -> str:
    try:
        meta = model_store.metadata(getattr(strategy, "_model_key", ""))
        return meta.model_hash if meta else ""
    except Exception:
        return ""


class StrategyTaskManager:
    """按 runtime 创建/移除 APScheduler 任务。"""

    def __init__(self) -> None:
        self._attached: set[str] = set()
        self._next_open_attached: set[str] = set()

    def attach(self, runtime: StrategyRuntime) -> None:
        runtime_id = str(getattr(runtime, "runtime_id", "") or "")
        if not runtime_id:
            return
        if str(getattr(runtime, "mode", "")) not in {"paper", "live"}:
            return
        if runtime_id in self._attached:
            return
        tracking_store.ensure_run(
            runtime_id,
            runtime.portfolio_id,
            backtest_id=str(getattr(runtime, "source_backtest_portfolio_id", "") or ""),
            start_date=datetime.date.today(),
            fill_timing=str((runtime.config or {}).get("fill_timing", "auction_close")),
            dry_run_enabled=True,
        )
        self._init_shadow_state(runtime)
        try:
            scheduler.add_job(
                self.run_eod,
                "cron",
                hour=_EOD_HOUR,
                minute=_EOD_MINUTE,
                day_of_week="mon-fri",
                args=[runtime_id],
                id=f"{_job_prefix(runtime_id)}:eod",
                name=f"strategy tracking eod {runtime_id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=None,
            )
            scheduler.add_job(
                self.run_morning,
                "cron",
                hour=_MORNING_HOUR,
                minute=_MORNING_MINUTE,
                day_of_week="mon-fri",
                args=[runtime_id],
                id=f"{_job_prefix(runtime_id)}:morning",
                name=f"strategy tracking morning {runtime_id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=None,
            )
            if str(getattr(runtime, "interval", "1d")) == "1d" and str(
                (runtime.config or {}).get("fill_timing", "")
            ).lower() in {"next_open", "open"}:
                scheduler.add_job(
                    self.run_next_open,
                    "cron",
                    hour=9,
                    minute=25,
                    day_of_week="mon-fri",
                    args=[runtime_id],
                    id=f"{_job_prefix(runtime_id)}:next_open",
                    name=f"strategy tracking next_open {runtime_id}",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=None,
                )
                self._next_open_attached.add(runtime_id)
                # A process may restart after the 09:25 trigger.  Reconcile
                # durable orders once at attach time; this submits an already
                # persisted intent only and never invokes the strategy.
                now = datetime.datetime.now()
                if now.time() >= datetime.time(9, 25):
                    self.run_next_open(runtime_id, now)
        except Exception as exc:  # pragma: no cover - 调度器未启动
            logger.warning("注册策略任务失败 {}: {}", runtime_id, exc)
            return
        self._attached.add(runtime_id)

    def detach(self, runtime_id: str) -> None:
        suffixes = ["eod", "morning"]
        if runtime_id in self._next_open_attached:
            suffixes.append("next_open")
        for suffix in suffixes:
            try:
                job = scheduler.scheduler.get_job(f"{_job_prefix(runtime_id)}:{suffix}")
                if job is not None:
                    scheduler.scheduler.remove_job(job.id)
            except Exception:
                pass
        self._attached.discard(runtime_id)
        self._next_open_attached.discard(runtime_id)

    def _init_shadow_state(self, runtime: StrategyRuntime) -> None:
        if tracking_store.get_shadow_state(runtime.runtime_id) is not None:
            return
        broker = getattr(runtime, "broker", None)
        cash = float(getattr(broker, "cash", 0) or 0)
        positions = []
        try:
            raw = getattr(broker, "positions", {}) or {}
            values = raw.values() if isinstance(raw, dict) else raw
            for pos in values:
                positions.append(
                    {
                        "asset": pos.asset,
                        "shares": float(pos.shares),
                        "avail": float(pos.avail),
                        "price": float(pos.price),
                        "mv": float(pos.mv),
                    }
                )
        except Exception:
            positions = []
        tracking_store.save_shadow_state(
            runtime.runtime_id,
            runtime.portfolio_id,
            cash=cash,
            positions=positions,
        )

    def _runtime(self, runtime_id: str) -> StrategyRuntime | None:
        from quantide.service.strategy_runtime import strategy_runtime_manager

        return strategy_runtime_manager.get_runtime(runtime_id)

    def _trading_day(self, now: datetime.datetime | None = None) -> datetime.date | None:
        now = now or datetime.datetime.now()
        try:
            if not calendar.is_trade_day(now):
                return None
            return now.date()
        except Exception:
            return now.date()

    def _can_replay(self, runtime: StrategyRuntime, day: datetime.date) -> bool:
        """只有 latest 模型在该日已生效时才允许回放，避免未来函数。"""
        try:
            meta = model_store.metadata(runtime.config.get("_model_key", ""))
        except Exception:
            meta = None
        if meta is None:
            # model_key 由策略实例计算；从 spec/config 无法直接得到时，允许尝试，
            # 由策略自身的 effective_from 校验兜底。
            return True
        try:
            effective = datetime.date.fromisoformat(str(meta.effective_from))
            return effective <= day
        except Exception:
            return True

    def _actual_snapshot(self, runtime: StrategyRuntime, day: datetime.date) -> None:
        broker = getattr(runtime, "broker", None)
        if broker is None:
            return
        try:
            asset = broker.asset
            raw = getattr(broker, "positions", {}) or {}
            values = raw.values() if isinstance(raw, dict) else raw
            positions = [
                {
                    "asset": pos.asset,
                    "shares": float(pos.shares),
                    "avail": float(pos.avail),
                    "price": float(pos.price),
                    "mv": float(pos.mv),
                }
                for pos in values
            ]
        except Exception as exc:
            logger.warning("实际账户快照失败 {}: {}", runtime.runtime_id, exc)
            return
        tracking_store.save_daily(
            runtime_id=runtime.runtime_id,
            portfolio_id=runtime.portfolio_id,
            day=day,
            source="actual",
            nav=float(getattr(asset, "total", 0) or 0),
            cash=float(getattr(asset, "cash", 0) or 0),
            market_value=float(getattr(asset, "market_value", 0) or 0),
            positions=positions,
        )

    def _run_shadow(self, runtime: StrategyRuntime, day: datetime.date) -> dict[str, Any] | None:
        config = dict(runtime.config or {})
        fill_timing = str(config.get("fill_timing", "auction_close"))
        if fill_timing not in _SUPPORTED_FILL_TIMINGS:
            logger.info(
                "dry-run 暂不支持 fill_timing={}，跳过 {}",
                fill_timing,
                runtime.runtime_id,
            )
            return None
        state = tracking_store.get_shadow_state(runtime.runtime_id) or {}
        broker = ShadowBroker(
            portfolio_id=runtime.portfolio_id,
            principal=float(getattr(runtime, "principal", 0) or 0),
            config=config,
            trade_date=day,
            cash=float(state.get("cash") or 0),
            positions=list(state.get("positions") or []),
            portfolio_name=f"{runtime.portfolio_id}-dry-run",
        )
        broker.settle_t1()

        from quantide.service.discovery import strategy_loader

        strategy_cls = strategy_loader.load_from_cache().get(runtime.strategy_name)
        if strategy_cls is None:
            logger.warning("dry-run 策略不存在: {}", runtime.strategy_name)
            return None
        strategy: Any = strategy_cls(broker, {**config, "_shadow_mode": True})
        try:
            asyncio.run(strategy.init())
            # 回放日必须有一份当天已生效的模型；否则不要用未来模型。
            if hasattr(strategy, "_load_model_from_store"):
                strategy._model = None
                if not strategy._load_model_from_store(day):
                    logger.warning(
                        "dry-run 缺少 {} 生效的模型，记为缺口: {}",
                        day,
                        runtime.runtime_id,
                    )
                    return None
            if fill_timing in {"next_open", "open"}:
                from quantide.service.strategy_runtime import NextOpenBrokerProxy

                strategy.broker = NextOpenBrokerProxy(
                    broker,
                    runtime_id=f"{runtime.runtime_id}:shadow",
                    portfolio_id=runtime.portfolio_id,
                    strategy_id=f"{getattr(runtime, 'strategy_id', '')}:shadow",
                    signal_date=day,
                )
                decision_time = datetime.time(15, 0)
            else:
                decision_time = datetime.time(14, 57)
            asyncio.run(strategy.on_bar(datetime.datetime.combine(day, decision_time)))
            if getattr(strategy, "_data_missing", False):
                logger.warning("dry-run 行情缺失，记为缺口: {} {}", runtime.runtime_id, day)
                return None
        except Exception as exc:
            logger.exception("dry-run 运行失败 {}: {}", runtime.runtime_id, exc)
            return None

        positions = [
            {
                "asset": asset,
                "shares": float(pos.shares),
                "avail": float(pos.avail),
                "price": float(pos.price),
                "mv": float(pos.mv),
            }
            for asset, pos in broker.positions.items()
        ]
        tracking_store.save_shadow_state(
            runtime.runtime_id,
            runtime.portfolio_id,
            cash=broker.cash,
            positions=positions,
        )
        nav = broker.total_assets
        tracking_store.save_daily(
            runtime_id=runtime.runtime_id,
            portfolio_id=runtime.portfolio_id,
            day=day,
            source="dry_run",
            nav=nav,
            cash=broker.cash,
            market_value=nav - broker.cash,
            positions=positions,
            trades=broker.trades,
            model_hash=_model_hash(strategy),
        )
        return {
            "nav": nav,
            "cash": broker.cash,
            "positions": positions,
            "trades": list(broker.trades),
            "model_hash": _model_hash(strategy),
        }

    def _process_shadow_intents(self, runtime: StrategyRuntime, day: datetime.date) -> int:
        """Drain shadow next-open intents against the target day's open."""
        shadow_runtime_id = f"{runtime.runtime_id}:shadow"
        rows = tracking_store.list_next_open_intents(runtime_id=shadow_runtime_id, target_date=day)
        if not rows:
            return 0
        config = dict(runtime.config or {})
        state = tracking_store.get_shadow_state(runtime.runtime_id) or {}
        broker = ShadowBroker(
            portfolio_id=runtime.portfolio_id,
            principal=float(getattr(runtime, "principal", 0) or 0),
            config=config,
            trade_date=day,
            cash=float(state.get("cash") or 0),
            positions=list(state.get("positions") or []),
            portfolio_name=f"{runtime.portfolio_id}-dry-run",
        )
        broker.settle_t1()
        order_time = datetime.datetime.combine(day, datetime.time(9, 25))
        for row in rows:
            try:
                kwargs = dict(row.get("kwargs") or {})
                kwargs["order_time"] = order_time
                method = getattr(broker, str(row["method"]))
                asyncio.run(method(*(row.get("args") or []), **kwargs))
                tracking_store.mark_next_open_intent(row["intent_id"], status="processed")
            except Exception as exc:
                tracking_store.mark_next_open_intent(
                    row["intent_id"], status="failed", error=str(exc)
                )
                logger.warning("shadow next_open intent 执行失败 {}: {}", row["intent_id"], exc)
        positions = [
            {
                "asset": asset,
                "shares": float(pos.shares),
                "avail": float(pos.avail),
                "price": float(pos.price),
                "mv": float(pos.mv),
            }
            for asset, pos in broker.positions.items()
        ]
        tracking_store.save_shadow_state(
            runtime.runtime_id,
            runtime.portfolio_id,
            cash=broker.cash,
            positions=positions,
        )
        tracking_store.save_daily(
            runtime_id=runtime.runtime_id,
            portfolio_id=runtime.portfolio_id,
            day=day,
            source="dry_run",
            nav=broker.total_assets,
            cash=broker.cash,
            market_value=broker.total_assets - broker.cash,
            positions=positions,
            trades=broker.trades,
        )
        return len(rows)

    def _ensure_model(self, runtime: StrategyRuntime, day: datetime.date) -> None:
        try:
            from quantide.service.discovery import strategy_loader

            strategy_cls = strategy_loader.load_from_cache().get(runtime.strategy_name)
            if strategy_cls is None:
                return
            strategy: Any = strategy_cls(runtime.broker, dict(runtime.config or {}))
            if not hasattr(strategy, "train_model_for_day"):
                return
            # 只对模型策略生效；没有模型或已到期才训练。
            if strategy._load_model_from_store(day) and not strategy._model_due(day):
                return
            strategy.train_model_for_day(day)
        except Exception as exc:
            logger.warning("模型维护失败 {}: {}", runtime.runtime_id, exc)

    def _ensure_model_effective_today(
        self, runtime: StrategyRuntime, today: datetime.date, previous: datetime.date
    ) -> None:
        """早盘兜底：只保证今天有可用模型，训练数据截止到上一交易日。"""
        try:
            from quantide.service.discovery import strategy_loader

            strategy_cls = strategy_loader.load_from_cache().get(runtime.strategy_name)
            if strategy_cls is None:
                return
            strategy: Any = strategy_cls(runtime.broker, dict(runtime.config or {}))
            if not hasattr(strategy, "train_model_for_day"):
                return
            if strategy._load_model_from_store(today) and not strategy._model_due(today):
                return
            strategy.train_model_for_day(previous)
        except Exception as exc:
            logger.warning("早盘模型兜底失败 {}: {}", runtime.runtime_id, exc)

    def run_eod(self, runtime_id: str) -> None:
        runtime = self._runtime(runtime_id)
        if runtime is None or runtime.status != "running":
            return
        day = self._trading_day()
        if day is None:
            return
        run = tracking_store.get_run(runtime_id) or {}
        shadow = None
        if run.get("dry_run_enabled", True):
            shadow = self._run_shadow(runtime, day)
        self._actual_snapshot(runtime, day)
        self._ensure_model(runtime, day)
        gaps = list(run.get("gap_dates") or [])
        if run.get("dry_run_enabled", True) and shadow is None:
            if day.isoformat() not in gaps:
                gaps.append(day.isoformat())
        tracking_store.update_run(
            runtime_id,
            last_tracking_date=day.isoformat(),
            fill_timing=str((runtime.config or {}).get("fill_timing", "auction_close")),
            gap_dates=gaps,
        )

    def run_morning(self, runtime_id: str) -> None:
        runtime = self._runtime(runtime_id)
        if runtime is None or runtime.status != "running":
            return
        day = self._trading_day()
        if day is None:
            return
        if (
            str((runtime.config or {}).get("fill_timing", "")).lower() in {"next_open", "open"}
            and str(getattr(runtime, "interval", "1d")) == "1d"
        ):
            self._process_shadow_intents(runtime, day)
        run = tracking_store.get_run(runtime_id) or {}
        last = str(run.get("last_tracking_date") or "")
        try:
            previous = calendar.day_shift(day, -1)
        except Exception:
            previous = day - datetime.timedelta(days=1)
        _replay_previous_shadow_session(self, run, last, previous, runtime, runtime_id)
        self._ensure_model_effective_today(runtime, day, previous)

    def run_next_open(self, runtime_id: str, now: datetime.datetime | None = None) -> None:
        """Submit durable 1d intents at the next trading day's open."""
        runtime = self._runtime(runtime_id)
        if runtime is None or runtime.status != "running":
            return
        try:
            from quantide.service.strategy_runtime import strategy_runtime_manager

            asyncio.run(strategy_runtime_manager.process_next_open_intents(runtime_id, now))
        except Exception as exc:
            logger.warning("next_open 任务失败 {}: {}", runtime_id, exc)


strategy_task_manager = StrategyTaskManager()

__all__ = ["StrategyTaskManager", "strategy_task_manager"]
