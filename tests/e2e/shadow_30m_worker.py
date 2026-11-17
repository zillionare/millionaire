"""Child-process driver for the 30m shadow ledger integration evidence."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl

SLOT_TIMES = (
    datetime.time(10, 0),
    datetime.time(10, 30),
    datetime.time(11, 0),
    datetime.time(11, 30),
    datetime.time(13, 30),
    datetime.time(14, 0),
    datetime.time(14, 30),
    datetime.time(15, 0),
)
DAYS = (datetime.date(2024, 1, 2), datetime.date(2024, 1, 3))
ASSET = "000001.SZ"


def slots() -> list[datetime.datetime]:
    return [datetime.datetime.combine(day, moment) for day in DAYS for moment in SLOT_TIMES]


def parse_slot(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("+08:00", "")).replace(tzinfo=None)


def frame_for(slot: datetime.datetime) -> pl.DataFrame | None:
    rows = []
    for asset, price in (("000001.SZ", 10.0), ("000002.SZ", 20.0)):
        rows.append(
            {
                "date": [slot],
                "asset": [asset],
                "open": [price],
                "high": [price],
                "low": [price],
                "close": [price],
                "volume": [1_000_000.0],
                "amount": [10_000_000.0],
                "is_st": [False],
                "up_limit": [price * 1.1],
                "down_limit": [price * 0.9],
            }
        )
    return pl.concat([pl.DataFrame(row) for row in rows])


def with_calendar(module: Any) -> None:
    ordered = slots()
    following = dict(zip(ordered, ordered[1:], strict=False))
    module.calendar.is_trade_day = lambda _day: True
    module.calendar.floor = lambda now, _frame: now
    module.calendar.shift = lambda item, *_args: following.get(
        item, item + datetime.timedelta(minutes=30)
    )


def runtime() -> SimpleNamespace:
    return SimpleNamespace(
        runtime_id="paper:p1",
        portfolio_id="p1",
        strategy_name="ShadowLedgerWorker",
        strategy_id="s1",
        mode="paper",
        status="running",
        interval="30m",
        symbols=["000001.SZ", "000002.SZ"],
        config={
            "fill_timing": "next_open",
            "slippage_pct": 0.0,
            "commission": 0.001,
            "min_commission": 5.0,
            "transfer_fee": 0.00001,
            "stamp_duty": 0.0005,
        },
        principal=10_000.0,
        broker=None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--latest", required=True)
    parser.add_argument("--start-slot", default="")
    parser.add_argument("--missing", default="")
    parser.add_argument("--kill-slot", default="")
    parser.add_argument("--kill-stage", choices=("before", "after"), default="after")
    parser.add_argument("--observed-file", required=True)
    args = parser.parse_args()

    from quantide.service import shadow_intraday as module
    from quantide.service.model_store import ModelStore
    from quantide.service.shadow_intraday import IntradayShadowRunner
    from quantide.service.strategy_runtime import StrategyRuntimeManager
    from quantide.service.strategy_tracking import TrackingStore, bar_slot_text

    with_calendar(module)
    latest = parse_slot(args.latest)
    StrategyRuntimeManager._latest_completed_30m_bar = staticmethod(  # type: ignore[method-assign,assignment]
        lambda _now: latest
    )
    missing = {parse_slot(value) for value in args.missing.split(",") if value}
    store = TrackingStore(args.db)
    store.ensure_run(
        "paper:p1",
        "p1",
        start_date=DAYS[0],
        fill_timing="next_open",
        bar_interval="30m",
        start_slot=bar_slot_text(slots()[0]),
    )
    if args.start_slot:
        store.update_run("paper:p1", shadow_start_slot=bar_slot_text(parse_slot(args.start_slot)))
    if store.get_shadow_state("paper:p1") is None:
        store.save_shadow_state("paper:p1", "p1", cash=10_000.0, positions=[])
    observed = Path(args.observed_file)
    models = ModelStore(Path(args.models))

    class Strategy:
        def __init__(self, broker: Any, config: dict[str, Any]) -> None:
            self.broker = broker
            self.config = config
            self._model_ref = str(config.get("_model_ref") or "")
            payload, _ = models.load_ref(self._model_ref)
            if not isinstance(payload, dict):
                raise RuntimeError(f"shadow model ref is not loadable: {self._model_ref}")
            self.loaded_generation = str(payload.get("generation") or "")

        async def on_bar(self, bar: datetime.datetime) -> None:
            day1_1000 = datetime.datetime(2024, 1, 2, 10, 0)
            day1_1030 = datetime.datetime(2024, 1, 2, 10, 30)
            day1_1430 = datetime.datetime(2024, 1, 2, 14, 30)
            day2_1000 = datetime.datetime(2024, 1, 3, 10, 0)
            day2_1030 = datetime.datetime(2024, 1, 3, 10, 30)
            if bar == day1_1000:
                await self.broker.buy(ASSET, 100)
            elif bar == day1_1030:
                await self.broker.sell(ASSET, 100)
            elif bar == day1_1430:
                await self.broker.buy(ASSET, 100)
            elif bar == day2_1000:
                await self.broker.sell(ASSET, 100)
            elif bar == day2_1030:
                await self.broker.sell(ASSET, 100)
            current = bar.replace(tzinfo=None).isoformat(timespec="seconds")
            pending = sum(
                1
                for row in store.list_next_open_intents(
                    runtime_id="paper:p1:shadow", status="pending"
                )
                if str(row.get("target_bar") or "") >= current
            )
            with observed.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "slot": bar_slot_text(bar),
                            "model_ref": self._model_ref,
                            "loaded_generation": self.loaded_generation,
                            "pending": pending,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    def _build(_runtime: Any, broker: Any, _day: Any, config: dict[str, Any]) -> Any:
        try:
            return Strategy(broker, config)
        except Exception as exc:
            with observed.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {"slot": config.get("_bar_slot", ""), "error": str(exc)},
                        sort_keys=True,
                    )
                    + "\n"
                )
            return None

    module.build_shadow_strategy = _build  # type: ignore[assignment]
    runner = IntradayShadowRunner(store)
    runner.frame = lambda item, _runtime: (  # type: ignore[method-assign,assignment]
        None if item in missing else frame_for(item)
    )

    kill_slot = parse_slot(args.kill_slot) if args.kill_slot else None
    original_advance = store.advance_intraday_slot

    def checked(**kwargs: Any) -> None:
        if kill_slot is not None and kwargs.get("bar_slot") == bar_slot_text(kill_slot):
            if args.kill_stage == "before":
                os.kill(os.getpid(), signal.SIGKILL)
            original_advance(**kwargs)
            if args.kill_stage == "after":
                os.kill(os.getpid(), signal.SIGKILL)
            return
        original_advance(**kwargs)

    store.advance_intraday_slot = checked  # type: ignore[method-assign]
    runner.run(runtime(), latest)  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
