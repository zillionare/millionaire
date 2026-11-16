"""Claim, submit and reconcile durable next-open intents."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from quantide.core.errors import TradeError
from quantide.core.order_identity import client_order_id
from quantide.data.models.calendar import calendar
from quantide.service.intent_execution import reconcile_processing_intents
from quantide.service.runtime_proxies import (
    StrategyBrokerProxy,
)

if TYPE_CHECKING:
    from quantide.service.runtime_models import StrategyRuntime
    from quantide.service.strategy_tracking import TrackingStore


class RuntimeIntentExecution:
    """Claim, submit and reconcile durable next-open intents."""

    if TYPE_CHECKING:

        @property
        def tracking_store(self) -> TrackingStore: ...

        def get_runtime(self, runtime_id: str) -> StrategyRuntime | None: ...

    async def process_next_open_30m_intents(
        self, runtime_id: str, completed_bar: datetime.datetime
    ) -> int:
        """Submit durable 30m intents whose target bar has completed.

        Claim before submission. Uncertain processing rows require reconciliation;
        processed rows are never selected again, including after restart.
        """
        runtime = self.get_runtime(runtime_id)
        if runtime is None or runtime.status not in {"running", "stopping"}:
            return 0
        if str(getattr(runtime, "interval", "")) != "30m":
            return 0
        boundary = completed_bar.replace(tzinfo=None)
        reconcile_processing_intents(runtime_id, runtime.broker, self.tracking_store)
        try:
            if not calendar.is_trade_day(boundary):
                return 0
        except Exception:
            # Test doubles and a not-yet-loaded calendar are handled by the
            # same fail-closed target calculation in the enqueue path.
            pass
        tm = boundary.time()
        if (
            tm < datetime.time(9, 30)
            or datetime.time(11, 30) < tm < datetime.time(13, 0)
            or tm > datetime.time(15, 0)
        ):
            return 0
        broker = runtime.broker
        if runtime.mode == "live":
            broker = StrategyBrokerProxy(runtime.broker, runtime.strategy_id)
        rows = self.tracking_store.list_next_open_intents(
            runtime_id=runtime_id, target_bar=boundary
        )
        return await self._submit_intent_rows(broker, rows, boundary)

    async def process_next_open_intents(
        self, runtime_id: str, now: datetime.datetime | None = None
    ) -> int:
        """Submit due durable intents once at the next trading day's open."""
        runtime = self.get_runtime(runtime_id)
        current = now or datetime.datetime.now()
        if runtime is None or runtime.status not in {"running", "stopping"}:
            return 0
        if current.time() < datetime.time(9, 25):
            return 0
        reconcile_processing_intents(runtime_id, runtime.broker, self.tracking_store)
        # The persisted target date is the source of truth here.  A freshly
        # installed process may not have the calendar row for that date yet;
        # rejecting the durable intent in that case would strand an order.
        broker = runtime.broker
        if runtime.mode == "live":
            broker = StrategyBrokerProxy(runtime.broker, runtime.strategy_id)
        rows = self.tracking_store.list_next_open_intents(
            runtime_id=runtime_id, target_date=current.date()
        )
        return await self._submit_intent_rows(broker, rows, current)

    async def _submit_intent_rows(
        self, broker: Any, rows: list[dict[str, Any]], current: datetime.datetime
    ) -> int:
        """Keep uncertain outcomes in processing for broker reconciliation on the next drain."""
        submitted = 0
        for pending in rows:
            row = self.tracking_store.claim_next_open_intent(pending["intent_id"])
            if row is None:
                continue
            try:
                await self._submit_claimed_intent(broker, row, current)
                self.tracking_store.mark_next_open_intent(row["intent_id"], status="processed")
                submitted += 1
            except Exception as exc:
                # A transport timeout may occur after acceptance. Only a definitive
                # domain rejection can be terminal; unknown results require reconciliation.
                status = "failed" if isinstance(exc, TradeError) else "processing"
                self.tracking_store.mark_next_open_intent(
                    row["intent_id"], status=status, error=str(exc)
                )
                logger.warning("next_open intent {} {}: {}", status, row["intent_id"], exc)
        return submitted

    @staticmethod
    async def _submit_claimed_intent(
        broker: Any, row: dict[str, Any], current: datetime.datetime
    ) -> None:
        kwargs = dict(row.get("kwargs") or {})
        target = row.get("target_bar")
        target_time = datetime.datetime.fromisoformat(target) if target else current
        kwargs["order_time"] = max(target_time, current)
        method = getattr(broker, str(row["method"]))
        token = client_order_id.set(row["intent_id"])
        try:
            await method(*(row.get("args") or []), **kwargs)
        finally:
            client_order_id.reset(token)
