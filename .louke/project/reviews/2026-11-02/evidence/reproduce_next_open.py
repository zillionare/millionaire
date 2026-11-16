import asyncio
import datetime
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from quantide.core.message import msg_hub
from quantide.service.strategy_runtime import StrategyRuntimeManager
from quantide.service.strategy_tracking import tracking_store


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        tracking_store.rebind(Path(tmp) / "review.db")
        rid = "paper:review:s"
        calls = []

        class Broker:
            async def buy(self, *args, **kwargs):
                calls.append("accepted")

        rt = SimpleNamespace(runtime_id=rid, status="running", broker=Broker(), mode="paper")
        manager = StrategyRuntimeManager()
        manager._strategy_runtimes[rid] = rt
        tracking_store.enqueue_next_open_intent(
            runtime_id=rid,
            portfolio_id="review",
            strategy_id="s",
            signal_date=datetime.date(2024, 1, 2),
            target_date=datetime.date(2024, 1, 3),
            method="buy",
            args=["000001.SZ", 100],
            kwargs={"price": 10},
            intent_key="stable",
        )
        with patch.object(
            tracking_store, "mark_next_open_intent", side_effect=SystemExit("power loss before ack")
        ):
            try:
                await manager.process_next_open_intents(rid, datetime.datetime(2024, 1, 3, 10))
            except SystemExit:
                pass
        print(
            "AFTER_CRASH_WINDOW",
            len(calls),
            tracking_store.list_next_open_intents(runtime_id=rid)[0]["status"],
        )
        await manager.process_next_open_intents(rid, datetime.datetime(2024, 1, 3, 10, 1))
        print(
            "AFTER_RETRY",
            json.dumps(
                {
                    "broker_accepted_count": len(calls),
                    "processed_count": len(
                        tracking_store.list_next_open_intents(runtime_id=rid, status="processed")
                    ),
                }
            ),
        )
    msg_hub.stop()


asyncio.run(main())
