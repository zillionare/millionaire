"""Reconcile durable next-open orders before allowing a retry."""

from typing import Any

from quantide.service.strategy_tracking import TrackingStore


def reconcile_processing_intents(runtime_id: str, broker: Any, store: TrackingStore) -> None:
    """Resolve accepted orders; retry only with an idempotent broker contract."""
    rows = store.list_next_open_intents(runtime_id=runtime_id, status="processing")
    if not rows:
        return
    if getattr(broker, "supports_idempotent_orders", False) is not True:
        raise RuntimeError("next_open 存在未确认的 processing intent，需对账，拒绝重提交")
    for row in rows:
        order = broker.find_order_by_client_id(row["intent_id"])
        store.mark_next_open_intent(
            row["intent_id"], status="processed" if order is not None else "pending"
        )
