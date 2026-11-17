"""Closed-bar 30-minute Shadow-Run replay and gap handling."""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

from quantide.core.enums import FrameType
from quantide.core.market_time import market_now
from quantide.data.models.calendar import calendar
from quantide.data.models.minute_bars import minute_bars
from quantide.service.model_store import model_store
from quantide.service.shadow_broker import ShadowBroker
from quantide.service.shadow_support import (
    build_shadow_strategy,
    position_snapshots,
    runtime_symbols,
)
from quantide.service.strategy_tracking import (
    TrackingStore,
    bar_slot_text,
    tracking_store,
)

if TYPE_CHECKING:
    from quantide.service.runtime_models import StrategyRuntime

SESSION_SLOT_TIMES = {
    datetime.time(10, 0),
    datetime.time(10, 30),
    datetime.time(11, 0),
    datetime.time(11, 30),
    datetime.time(13, 30),
    datetime.time(14, 0),
    datetime.time(14, 30),
    datetime.time(15, 0),
}
_NEXT_OPEN_TIMINGS = {"next_open", "open"}


def parse_bar_slot(value: str) -> datetime.datetime | None:
    """Parse the persisted +08:00 slot back to a naive exchange-local datetime."""
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def next_session_slot(slot: datetime.datetime) -> datetime.datetime:
    """Move to the next real 30m close, skipping lunch and overnight gaps."""
    shifted = calendar.shift(slot, 1, FrameType.MIN30)
    if not isinstance(shifted, datetime.datetime):
        raise RuntimeError("30m calendar did not return a datetime")
    return shifted.replace(tzinfo=None)


def _exchange_naive(value: datetime.datetime) -> datetime.datetime:
    """Convert any aware input to exchange-local naive time; keep naive input as-is."""
    if value.tzinfo is None:
        return value
    return value.astimezone(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)


def _previous_session_close(day: datetime.date) -> datetime.datetime | None:
    current = day
    for _ in range(10):
        try:
            current = calendar.day_shift(current, -1)
        except Exception:
            current = current - datetime.timedelta(days=1)
        try:
            if calendar.is_trade_day(current):
                return datetime.datetime.combine(current, datetime.time(15, 0))
        except Exception:
            continue
    return None


def latest_closed_session_slot(now: datetime.datetime | None = None) -> datetime.datetime | None:
    """Return the latest closed slot, including previous-session backlog before 10:00."""
    from quantide.service.strategy_runtime import StrategyRuntimeManager

    current = _exchange_naive(now or market_now())
    candidate = StrategyRuntimeManager._latest_completed_30m_bar(current)
    if candidate is not None and candidate.time() in SESSION_SLOT_TIMES:
        return candidate
    return _previous_session_close(current.date())


def _first_slot_where(current: datetime.datetime, predicate: Any) -> datetime.datetime | None:
    for day_offset in range(10):
        day = current.date() + datetime.timedelta(days=day_offset)
        if not predicate(day):
            continue
        for slot in sorted(SESSION_SLOT_TIMES):
            candidate = datetime.datetime.combine(day, slot)
            if candidate >= current:
                return candidate
    return None


def _is_trade_day(day: datetime.date) -> bool:
    try:
        return bool(calendar.is_trade_day(day))
    except Exception:
        return False


def first_slot_at_or_after(moment: datetime.datetime) -> datetime.datetime | None:
    """Return the first authoritative exchange slot, never inventing weekdays."""
    return _first_slot_where(_exchange_naive(moment), _is_trade_day)


def _closed_bucket(frame: pl.DataFrame, bar_slot: datetime.datetime) -> pl.DataFrame:
    return frame.filter(pl.col("date").cast(pl.Datetime("ms")) == bar_slot)


def load_closed_bar_frame(
    bar_slot: datetime.datetime,
    symbols: list[str],
    *,
    minute_model: Any | None = None,
) -> pl.DataFrame | None:
    """Load exactly one persisted closed bucket; never invent a forming bar."""
    model = minute_model or minute_bars
    try:
        frame = model.get_bars_in_range(
            bar_slot.date(), bar_slot.date(), assets=symbols or None, adjust="qfq"
        )
    except Exception as exc:
        logger.warning("30m shadow 读取分钟线失败 {}: {}", bar_slot, exc)
        return None
    if not isinstance(frame, pl.DataFrame) or frame.is_empty():
        return None
    frame = _closed_bucket(frame, bar_slot)
    if frame.is_empty():
        return None
    if symbols:
        present = set(frame["asset"].to_list())
        if any(asset not in present for asset in symbols):
            return None
    return frame.sort("asset")


def _model_hash(strategy: object) -> str:
    try:
        meta = model_store.metadata(getattr(strategy, "_model_key", ""))
        return meta.model_hash if meta else ""
    except Exception:
        return ""


class IntradayShadowRunner:
    """Replay closed 30m bars into an isolated shadow account."""

    def __init__(
        self,
        store: TrackingStore | None = None,
        *,
        minute_model: Any | None = None,
    ) -> None:
        self.store = store or tracking_store
        self.minute_model = minute_model

    def frame(self, bar_slot: datetime.datetime, runtime: StrategyRuntime) -> pl.DataFrame | None:
        return load_closed_bar_frame(
            bar_slot, runtime_symbols(runtime), minute_model=self.minute_model
        )

    def _default_start(
        self,
        run: dict[str, Any],
        last: datetime.datetime | None,
        now: datetime.datetime | None,
    ) -> datetime.datetime | None:
        if last is not None:
            return next_session_slot(last)
        try:
            started = datetime.datetime.combine(
                datetime.date.fromisoformat(str(run.get("start_date") or "")),
                datetime.time.min,
            )
        except ValueError:
            started = now or market_now()
        return first_slot_at_or_after(started)

    def _shadow_start(
        self,
        runtime: StrategyRuntime,
        run: dict[str, Any],
        last: datetime.datetime | None,
        now: datetime.datetime | None,
    ) -> datetime.datetime | None:
        start = parse_bar_slot(str(run.get("shadow_start_slot") or ""))
        if start is not None:
            return start
        default_start = self._default_start(run, last, now)
        if default_start is None:
            return None
        return parse_bar_slot(
            self.store.set_shadow_anchor(runtime.runtime_id, bar_slot_text(default_start))
        )

    def run(self, runtime: StrategyRuntime, now: datetime.datetime | None = None) -> int:
        """Advance every ready slot in order; stop at the first missing bucket."""
        run = self.store.get_run(runtime.runtime_id) or {}
        if not run.get("dry_run_enabled", True) or str(runtime.interval) != "30m":
            return 0
        latest = latest_closed_session_slot(now)
        if latest is None:
            return 0
        last = parse_bar_slot(str(run.get("last_tracking_slot") or ""))
        start = self._shadow_start(runtime, run, last, now)
        if start is None:
            return 0
        cursor = next_session_slot(last) if last is not None else start
        if cursor < start:
            cursor = start
        gaps = [str(item) for item in run.get("gap_slots") or []]
        processed = 0
        while cursor <= latest and self._advance_slot(runtime, cursor, gaps):
            processed += 1
            cursor = next_session_slot(cursor)
        return processed

    def _advance_slot(
        self, runtime: StrategyRuntime, cursor: datetime.datetime, gaps: list[str]
    ) -> bool:
        slot_text = bar_slot_text(cursor)
        frame = self.frame(cursor, runtime)
        result = self._replay(runtime, cursor, frame) if frame is not None else None
        if result is None:
            if slot_text not in gaps:
                gaps.append(slot_text)
            self.store.update_run(runtime.runtime_id, gap_slots=gaps, bar_interval="30m")
            return False
        if slot_text in gaps:
            gaps.remove(slot_text)
        bars = [result.pop("dry_run")]
        actual = self._actual_bar(runtime, cursor)
        if actual is not None:
            bars.append(actual)
        self.store.advance_intraday_slot(
            runtime_id=runtime.runtime_id,
            portfolio_id=runtime.portfolio_id,
            bar_slot=slot_text,
            bar_interval="30m",
            gap_slots=gaps,
            bars=bars,
            shadow_state=result.get("shadow_state"),
            processed_intent_ids=result.get("processed_intent_ids"),
        )
        return True

    def _replay(
        self, runtime: StrategyRuntime, bar_slot: datetime.datetime, frame: pl.DataFrame
    ) -> dict[str, Any] | None:
        state = self.store.get_shadow_state(runtime.runtime_id) or {}
        config = dict(runtime.config or {})
        actual = self.store.get_bar(runtime.runtime_id, bar_slot_text(bar_slot), source="actual")
        if actual and (actual.get("model_ref") or actual.get("model_hash")):
            config["_model_ref"] = str(actual.get("model_ref") or actual["model_hash"])
        broker = ShadowBroker(
            portfolio_id=runtime.portfolio_id,
            principal=float(getattr(runtime, "principal", 0) or 0),
            config=config,
            trade_date=bar_slot.date(),
            cash=float(state["cash"] if "cash" in state else getattr(runtime, "principal", 0) or 0),
            positions=list(state.get("positions") or []),
            portfolio_name=f"{runtime.portfolio_id}-dry-run",
            bar_interval="30m",
            bar_time=bar_slot,
            bar_frame=frame,
            minute_model=self.minute_model,
        )
        if self._new_session(state, bar_slot):
            broker.settle_t1()
        intent_ids = self._process_intents(runtime, broker, bar_slot)
        strategy = build_shadow_strategy(runtime, broker, bar_slot.date(), config)
        if strategy is None:
            return None
        try:
            if str(config.get("fill_timing", "")).lower() in _NEXT_OPEN_TIMINGS:
                from quantide.service.runtime_proxies import NextOpenBarBrokerProxy

                strategy.broker = NextOpenBarBrokerProxy(
                    broker,
                    runtime_id=f"{runtime.runtime_id}:shadow",
                    portfolio_id=runtime.portfolio_id,
                    strategy_id=f"{getattr(runtime, 'strategy_id', '')}:shadow",
                    signal_bar=bar_slot,
                    store=self.store,
                )
            asyncio.run(strategy.on_bar(bar_slot))
            if getattr(strategy, "_data_missing", False):
                return None
        except Exception as exc:
            logger.exception("30m dry-run 运行失败 {} {}: {}", runtime.runtime_id, bar_slot, exc)
            return None
        positions = position_snapshots(broker)
        state_bar = {
            "source": "dry_run",
            "nav": broker.total_assets,
            "cash": broker.cash,
            "market_value": broker.total_assets - broker.cash,
            "positions": positions,
            "trades": list(broker.trades),
            "model_hash": _model_hash(strategy),
        }
        return {
            "dry_run": state_bar,
            "shadow_state": {"cash": broker.cash, "positions": positions},
            "processed_intent_ids": intent_ids,
        }

    @staticmethod
    def _new_session(state: dict[str, Any], bar_slot: datetime.datetime) -> bool:
        last = parse_bar_slot(str(state.get("last_bar_slot") or ""))
        return last is None or last.date() != bar_slot.date()

    def _process_intents(
        self, runtime: StrategyRuntime, broker: ShadowBroker, bar_slot: datetime.datetime
    ) -> list[str]:
        rows = self.store.list_next_open_intents(
            runtime_id=f"{runtime.runtime_id}:shadow", target_bar=bar_slot
        )
        processed: list[str] = []
        for row in rows:
            try:
                kwargs = dict(row.get("kwargs") or {})
                kwargs["order_time"] = bar_slot
                method = getattr(broker, str(row["method"]))
                asyncio.run(method(*(row.get("args") or []), **kwargs))
                processed.append(str(row["intent_id"]))
            except Exception as exc:
                self.store.mark_next_open_intent(row["intent_id"], status="failed", error=str(exc))
                logger.warning("30m shadow intent 执行失败 {}: {}", row["intent_id"], exc)
        return processed

    def _actual_bar(
        self, runtime: StrategyRuntime, bar_slot: datetime.datetime
    ) -> dict[str, Any] | None:
        """Use only the actual fact persisted at the real slot; never current broker state."""
        return self.store.get_bar(runtime.runtime_id, bar_slot_text(bar_slot), source="actual")


intraday_shadow_runner = IntradayShadowRunner()

__all__ = [
    "IntradayShadowRunner",
    "SESSION_SLOT_TIMES",
    "intraday_shadow_runner",
    "first_slot_at_or_after",
    "latest_closed_session_slot",
    "load_closed_bar_frame",
    "next_session_slot",
    "parse_bar_slot",
]
