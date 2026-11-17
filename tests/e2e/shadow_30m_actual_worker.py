"""Prepare real PaperBroker facts for the 30m ledger oracle."""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests.e2e.shadow_30m_worker import DAYS, parse_slot, slots, with_calendar

ASSET = "000001.SZ"
OTHER = "000002.SZ"
MODEL_KEY = "ledger-model"
SIGNAL_SLOTS = {
    datetime.datetime(2024, 1, 2, 10, 0): ("buy", ASSET, 100),
    datetime.datetime(2024, 1, 2, 10, 30): ("sell", ASSET, 100),
    datetime.datetime(2024, 1, 2, 14, 30): ("buy", ASSET, 100),
    datetime.datetime(2024, 1, 3, 10, 0): ("sell", ASSET, 100),
    datetime.datetime(2024, 1, 3, 10, 30): ("sell", ASSET, 100),
}


def _quote() -> dict[str, dict[str, float]]:
    return {
        ASSET: {"lastPrice": 10.0, "volume": 1_000_000.0},
        OTHER: {"lastPrice": 20.0, "volume": 1_000_000.0},
    }


async def _execute(broker: Any, method: str, args: list[Any], slot: datetime.datetime) -> Any:
    call = getattr(broker, method)
    task = asyncio.create_task(call(*args, order_time=slot))
    await asyncio.sleep(0)
    broker.on_quote(_quote())
    return await task


def _process_pending(store: Any, broker: Any, slot: datetime.datetime) -> None:
    rows = store.list_next_open_intents(
        runtime_id="paper:p1:actual", target_bar=slot, status="pending"
    )
    for row in rows:
        claimed = store.claim_next_open_intent(str(row["intent_id"]))
        if claimed is None:
            continue
        try:
            asyncio.run(_execute(broker, str(row["method"]), list(row.get("args") or []), slot))
        except Exception as exc:
            store.mark_next_open_intent(row["intent_id"], status="failed", error=str(exc))
        else:
            store.mark_next_open_intent(row["intent_id"], status="processed")


def _pending(store: Any) -> int:
    return len(store.list_next_open_intents(runtime_id="paper:p1:actual", status="pending"))


def _observe(path: Path, slot: datetime.datetime, bar: dict[str, Any], pending: int) -> None:
    held = next((item for item in bar["positions"] if item["asset"] == ASSET), None)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "slot": bar["bar_slot"],
                    "cash": bar["cash"],
                    "nav": bar["nav"],
                    "shares": float((held or {}).get("shares") or 0),
                    "avail": float((held or {}).get("avail") or 0),
                    "pending": pending,
                    "model_ref": bar["model_ref"],
                },
                sort_keys=True,
            )
            + "\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--observed-file", required=True)
    parser.add_argument("--skip-actual-slot", default="")
    args = parser.parse_args()

    from quantide.data.sqlite import db
    from quantide.service import runtime_proxies
    from quantide.service.model_store import ModelArtifact, ModelStore
    from quantide.service.runtime_proxies import NextOpenBarBrokerProxy
    from quantide.service.sim_broker import PaperBroker
    from quantide.service.strategy_session import StrategySession
    from quantide.service.strategy_tracking import TrackingStore, bar_slot_text

    with_calendar(runtime_proxies)
    db.init(Path(args.db))
    store = TrackingStore(args.db)
    store.ensure_run(
        "paper:p1",
        "p1",
        start_date=DAYS[0],
        fill_timing="next_open",
        bar_interval="30m",
        start_slot=bar_slot_text(slots()[0]),
    )
    models = ModelStore(Path(args.models))
    artifact = models.save(
        key=MODEL_KEY,
        model={"generation": "A", "asset": ASSET},
        metadata=ModelArtifact(
            model_key=MODEL_KEY,
            strategy_name="ShadowLedgerWorker",
            config_hash="actual-A",
            train_end="2024-01-01",
            effective_from="2024-01-01",
            pipeline_version="pipeline-A",
        ),
    )
    loaded, _ = models.load_ref(artifact.extra["model_ref"])
    if loaded != {"generation": "A", "asset": ASSET}:
        raise RuntimeError("actual model A does not load")

    broker = PaperBroker.create(
        "p1",
        principal=10_000.0,
        commission=0.001,
        stamp_tax=0.0005,
        transfer_fee=0.00001,
        min_commission=5.0,
        slippage=0.0,
        portfolio_name="ledger-actual",
    )
    runtime = SimpleNamespace(runtime_id="paper:p1", portfolio_id="p1")
    strategy = SimpleNamespace(_model_ref=str(artifact.extra["model_ref"]))
    session = StrategySession(
        SimpleNamespace(tracking_store=store, _lock=threading.RLock(), _runtime_specs={}),
        runtime,
        strategy,
        [],
        broker,
        "30m",
        "next_open",
        (None, None),
    )
    observed = Path(args.observed_file)
    skip = parse_slot(args.skip_actual_slot) if args.skip_actual_slot else None
    previous_day: datetime.date | None = None
    try:
        for slot in slots():
            broker.set_clock(slot)
            broker.on_limit({ASSET: {"up": 11.0, "down": 9.0}, OTHER: {"up": 22.0, "down": 18.0}})
            if previous_day is not None and slot.date() != previous_day:
                broker.settle_t1()
            previous_day = slot.date()
            _process_pending(store, broker, slot)
            signal = SIGNAL_SLOTS.get(slot)
            if signal is not None:
                method, asset, shares = signal
                proxy = NextOpenBarBrokerProxy(
                    broker,
                    runtime_id="paper:p1:actual",
                    portfolio_id="p1",
                    strategy_id="s1:actual",
                    signal_bar=slot,
                    store=store,
                )
                asyncio.run(getattr(proxy, method)(asset, shares))
            if slot == skip:
                continue
            session._record_actual_bar(slot)
            bar = store.get_bar("paper:p1", bar_slot_text(slot), source="actual")
            if bar is None:
                raise RuntimeError(f"actual capture missing {slot}")
            _observe(observed, slot, bar, _pending(store))
    finally:
        broker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
