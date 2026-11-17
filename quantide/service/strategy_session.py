"""One strategy's callbacks, risk checks and durable signal dispatch."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from quantide.service.strategy_tracking import bar_slot_text

if TYPE_CHECKING:
    from quantide.core.strategy import BaseStrategy, RiskStrategy
    from quantide.service.runtime_models import StrategyRuntime
    from quantide.service.strategy_runtime import StrategyRuntimeManager


def fill_timing(strategy_cls: type[Any], config: dict[str, Any] | None) -> str:
    """Resolve the documented configuration/class/default precedence once."""
    value = (config or {}).get("fill_timing", getattr(strategy_cls, "fill_timing", None))
    if value is None:
        defaults = getattr(strategy_cls, "default_config", None)
        if callable(defaults):
            value = defaults().get("fill_timing")
    return str(value or "").strip().lower()


class StrategySession:
    """Keep per-session state out of the runtime manager's scheduling loop."""

    def __init__(
        self,
        manager: StrategyRuntimeManager,
        runtime: StrategyRuntime,
        strategy: BaseStrategy,
        risks: list[RiskStrategy],
        broker: Any,
        interval: str,
        timing: str,
        proxies: tuple[Callable[..., Any], Callable[..., Any]],
    ) -> None:
        self.manager = manager
        self.runtime = runtime
        self.strategy = strategy
        self.risks = risks
        self.broker = broker
        self.interval = interval
        self.queued = timing in {"next_open", "open"}
        self.daily_proxy, self.bar_proxy = proxies
        self.risk_day: datetime.date | None = None
        self.last_bar: datetime.datetime | None = None
        self._actual_trade_mark = 0
        self.last_decision = self._load_decision()

    def _load_decision(self) -> datetime.date | None:
        with self.manager._lock:
            saved = (self.manager._runtime_specs.get(self.runtime.runtime_id) or {}).get(
                "last_decision_date", ""
            )
        try:
            return datetime.date.fromisoformat(saved) if saved else None
        except ValueError:
            return None

    async def start(self) -> None:
        """Initialize the host before the selected risk programs."""
        for strategy in [self.strategy, *self.risks]:
            await strategy.init()
            await strategy.on_start()

    async def stop(self) -> None:
        """Give every strategy an opportunity to release its own resources."""
        for strategy in [*self.risks, self.strategy]:
            try:
                await strategy.on_stop()
            except Exception:
                logger.exception("策略停止回调失败")

    async def tick(self, now: datetime.datetime) -> None:
        """Run risk checks before dispatching a new host signal."""
        if hasattr(self.runtime.broker, "set_clock"):
            self.runtime.broker.set_clock(now)
        self.strategy._current_time = now
        await self._check_risk(now)
        if self.interval == "30m":
            await self._minute_signal(now)
        elif self.interval == "1M":
            await self.strategy.on_bar(now)
        elif self.queued:
            await self._daily_signal(now)
        else:
            await self.strategy.on_bar(now)
        window = getattr(self.strategy, "_in_decision_window", None)
        if window is None or window(now):
            self.manager._sync_strategy_data_alarm(
                self.runtime, bool(getattr(self.strategy, "_data_missing", False))
            )

    async def _check_risk(self, now: datetime.datetime) -> None:
        if self.risks and self.risk_day != now.date():
            if self.risk_day is not None:
                for strategy in self.risks:
                    await strategy.on_day_close(now)
            for strategy in self.risks:
                await strategy.on_day_open(now)
            self.risk_day = now.date()
        for strategy in self.risks:
            await strategy.on_check(self.broker.positions, now)

    def _proxy(self, proxy_type: Callable[..., Any], **boundary: Any) -> Any:
        return proxy_type(
            self.broker,
            store=self.manager.tracking_store,
            runtime_id=self.runtime.runtime_id,
            portfolio_id=self.runtime.portfolio_id,
            strategy_id=self.runtime.strategy_id,
            **boundary,
        )

    async def _dispatch(self, tm: datetime.datetime, proxy: Any) -> None:
        original = self.strategy.broker
        self.strategy.broker = proxy
        try:
            self.strategy._current_time = tm
            await self.strategy.on_bar(tm)
        finally:
            self.strategy.broker = original

    def _signal_already_processed(self, completed: datetime.datetime) -> bool:
        store = self.manager.tracking_store
        slot = bar_slot_text(completed)
        if store.get_bar(self.runtime.runtime_id, slot, source="actual") is not None:
            return True
        run = store.get_run(self.runtime.runtime_id) or {}
        previous = str(run.get("last_signal_slot") or "")
        return bool(previous and previous >= slot)

    def _mark_late_missing(self, completed: datetime.datetime, now: datetime.datetime) -> bool:
        from quantide.service.shadow_intraday import latest_closed_session_slot

        latest = latest_closed_session_slot(now)
        if latest is None or completed >= latest:
            return False
        store = self.manager.tracking_store
        run = store.get_run(self.runtime.runtime_id) or {}
        gaps = [str(item) for item in run.get("gap_slots") or []]
        slot = bar_slot_text(completed)
        if slot not in gaps:
            gaps.append(slot)
        store.update_run(self.runtime.runtime_id, gap_slots=gaps)
        return True

    async def _minute_signal(self, now: datetime.datetime) -> None:
        completed = self.manager._latest_completed_30m_bar(now)
        if self.queued:
            await self.manager.process_next_open_30m_intents(self.runtime.runtime_id, now)
        if completed is None or completed == self.last_bar:
            return
        if self._signal_already_processed(completed):
            self.last_bar = completed
            return
        if self._mark_late_missing(completed, now):
            self.last_bar = completed
            return
        if self.queued:
            await self._dispatch(completed, self._proxy(self.bar_proxy, signal_bar=completed))
        else:
            self.strategy._current_time = completed
            await self.strategy.on_bar(completed)
        self._record_actual_bar(completed)
        self.manager.tracking_store.update_run(
            self.runtime.runtime_id, last_signal_slot=bar_slot_text(completed)
        )
        self.last_bar = completed

    def _previous_actual_trade_ids(self, runtime_id: str) -> set[str]:
        rows = self.manager.tracking_store.list_bars(runtime_id, source="actual")
        return {
            str(trade.get("tid") or "")
            for row in rows
            for trade in row.get("trades") or []
            if trade.get("tid")
        }

    @staticmethod
    def _fill_payload(
        trade: Any, completed: datetime.datetime, seen: set[str]
    ) -> dict[str, Any] | None:
        moment = getattr(trade, "tm", None)
        if isinstance(moment, datetime.datetime):
            if moment.tzinfo is not None:
                moment = moment.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                moment = moment.replace(tzinfo=None)
            if moment > completed:
                return None
        payload = trade.to_dict() if hasattr(trade, "to_dict") else dict(trade)
        tid = str(payload.get("tid") or "")
        return None if tid and tid in seen else payload

    def _actual_fills(self, broker: Any, completed: datetime.datetime) -> list[dict[str, Any]]:
        query = getattr(broker, "query_trades", None)
        raw = query() if callable(query) else list(getattr(broker, "trades", []) or [])
        seen = self._previous_actual_trade_ids(self.runtime.runtime_id)
        run = self.manager.tracking_store.get_run(self.runtime.runtime_id) or {}
        try:
            start_date = datetime.date.fromisoformat(str(run.get("start_date") or ""))
        except ValueError:
            start_date = None
        fills = [self._fill_payload(trade, completed, seen) for trade in raw]
        return [
            fill
            for fill in fills
            if fill is not None
            and (
                start_date is None
                or not isinstance(fill.get("tm"), (str, datetime.datetime))
                or str(fill.get("tm"))[:10] >= start_date.isoformat()
            )
        ]

    def _record_actual_bar(self, completed: datetime.datetime) -> None:
        """Persist the factual account after this real paper bar, once per bar."""
        broker = getattr(self, "broker", None)
        if broker is None:
            return
        slot_text = bar_slot_text(completed)
        store = self.manager.tracking_store
        if store.get_bar(self.runtime.runtime_id, slot_text, source="actual") is not None:
            return
        try:
            asset = broker.asset
            from quantide.service.shadow_support import position_snapshots

            positions = position_snapshots(broker)
            trades = self._actual_fills(broker, completed)
            model_ref = str(getattr(self.strategy, "_model_ref", "") or "")
            model_hash = model_ref.rsplit("/", 1)[-1] if model_ref else ""
            store.save_bar(
                runtime_id=self.runtime.runtime_id,
                portfolio_id=self.runtime.portfolio_id,
                bar_slot=slot_text,
                bar_interval="30m",
                source="actual",
                nav=float(getattr(asset, "total", 0) or 0),
                cash=float(getattr(asset, "cash", 0) or 0),
                market_value=float(getattr(asset, "market_value", 0) or 0),
                positions=positions,
                trades=trades,
                model_hash=model_hash,
                model_ref=model_ref,
                write_once=True,
            )
        except Exception as exc:
            logger.warning("实际 30m 快照失败 {}: {}", self.runtime.runtime_id, exc)

    async def _daily_signal(self, now: datetime.datetime) -> None:
        day = self.manager._next_open_decision_day(now)
        if day is None or day == self.last_decision:
            return
        await self._dispatch(now, self._proxy(self.daily_proxy, signal_date=day))
        self.last_decision = day
        with self.manager._lock:
            spec = self.manager._runtime_specs.get(self.runtime.runtime_id)
            if spec is not None:
                spec["last_decision_date"] = day.isoformat()
                self.manager._save_specs()
