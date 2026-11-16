import asyncio
import datetime
import json
import tempfile
from pathlib import Path

from quantide.core.message import msg_hub
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        db.init(Path(tmp) / "review.db")
        broker = PaperBroker.create(
            "review", principal=10000, commission=0, stamp_tax=0, min_commission=0
        )
        now = datetime.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        broker.set_clock(now)
        await broker.buy("000001.SZ", 100, price=10, timeout=0.001)
        broker._on_quote_update({"000001.SZ": {"lastPrice": 10, "volume": 1000}})
        broker.set_clock(now + datetime.timedelta(days=1))
        broker.settle_t1()
        await broker.sell("000001.SZ", 100, price=11, timeout=0.001)
        broker._on_quote_update({"000001.SZ": {"lastPrice": 11, "volume": 1000}})
        print(
            "AFTER_FULL_SELL",
            json.dumps(
                {
                    "memory_cash": broker.cash,
                    "memory_positions": list(broker.positions),
                    "db_cash": db.get_asset(portfolio_id="review").cash,
                    "db_positions": db.get_positions(portfolio_id="review")
                    .select("asset", "shares")
                    .to_dicts(),
                    "trades": list(db["trades"].count for _ in range(1)),
                }
            ),
        )
        broker.close()
        loaded = PaperBroker.load("review")
        print(
            "AFTER_RELOAD",
            json.dumps({"cash": loaded.cash, "positions": [p.asset for p in loaded.positions]}),
        )
        loaded.close()
        broker._persist_updates({"000001.SZ"})
        loaded = PaperBroker.load("review")
        print(
            "AFTER_FORCED_EMPTY_SNAPSHOT",
            json.dumps({"cash": loaded.cash, "positions": [p.asset for p in loaded.positions]}),
        )
        loaded.close()
        pending = PaperBroker.create("pending", principal=10000)
        pending.set_clock(now)
        result = await pending.buy("000001.SZ", 100, price=10, timeout=0.001)
        print(
            "PENDING_BEFORE_RELOAD",
            len(pending._active_orders["000001.SZ"]),
            db["orders"].get(result.qt_oid)["status"],
        )
        pending.close()
        loaded = PaperBroker.load("pending")
        print(
            "PENDING_AFTER_RELOAD",
            dict(loaded._active_orders),
            db["orders"].get(result.qt_oid)["status"],
        )
        loaded.close()
        db.close()
    msg_hub.stop()


asyncio.run(main())
