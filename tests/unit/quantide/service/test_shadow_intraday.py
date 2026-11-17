"""Closed-bar 30m Shadow-Run replay, gaps, T+1 and restart idempotency."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import polars as pl

from quantide.service.shadow_intraday import IntradayShadowRunner, load_closed_bar_frame
from quantide.service.strategy_tracking import TrackingStore, bar_slot_text


def _slot(day: int, hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, day, hour, minute)


def _frame(slot: datetime.datetime, price: float = 10.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": [slot],
            "asset": ["000001.SZ"],
            "open": [price],
            "high": [price + 0.1],
            "low": [price - 0.1],
            "close": [price],
            "volume": [100000.0],
            "amount": [1_000_000.0],
            "is_st": [False],
            "up_limit": [price * 1.1],
            "down_limit": [price * 0.9],
        }
    )


def _runtime():
    return SimpleNamespace(
        runtime_id="paper:p1",
        portfolio_id="p1",
        strategy_name="Dummy30m",
        strategy_id="s1",
        mode="paper",
        status="running",
        interval="30m",
        symbols=["000001.SZ"],
        config={"fill_timing": "next_open", "slippage_pct": 0.0},
        principal=100000.0,
        broker=None,
    )


def test_load_closed_bar_frame_ignores_forming_bucket():
    target = _slot(27, 10, 30)

    class _Minutes:
        @staticmethod
        def get_bars_in_range(start, end=None, assets=None, adjust=None, eager_mode=True):
            return pl.concat([_frame(_slot(27, 10, 0)), _frame(target), _frame(target + datetime.timedelta(minutes=30))])

    frame = load_closed_bar_frame(target, ["000001.SZ"], minute_model=_Minutes())
    assert frame is not None
    assert frame["date"].to_list() == [target]


def test_30m_ledger_replays_full_day_t1_gap_and_restart(tmp_path, monkeypatch):
    store = TrackingStore(tmp_path / "shadow-30m.db")
    slot = _slot(27, 10, 0)
    store.ensure_run(
        "paper:p1",
        "p1",
        start_date=slot.date(),
        fill_timing="next_open",
        bar_interval="30m",
    )
    store.save_shadow_state("paper:p1", "p1", cash=100000, positions=[])

    slots = [
        _slot(27, 10, 0),
        _slot(27, 10, 30),
        _slot(27, 11, 0),
        _slot(27, 11, 30),
        _slot(27, 13, 30),
        _slot(27, 14, 0),
        _slot(27, 14, 30),
        _slot(27, 15, 0),
        _slot(28, 10, 0),
        _slot(28, 10, 30),
        _slot(28, 11, 0),
        _slot(28, 11, 30),
        _slot(28, 13, 30),
        _slot(28, 14, 0),
        _slot(28, 14, 30),
        _slot(28, 15, 0),
    ]
    frames = {item: _frame(item, 10.0 + index * 0.1) for index, item in enumerate(slots)}
    import quantide.service.shadow_intraday as shadow_module

    next_by_slot = dict(zip(slots, slots[1:], strict=False))
    monkeypatch.setattr(shadow_module.calendar, "is_trade_day", lambda _: True)
    monkeypatch.setattr(shadow_module.calendar, "floor", lambda now, _: now)
    monkeypatch.setattr(shadow_module.calendar, "shift", lambda item, *_: next_by_slot[item])
    runner = IntradayShadowRunner(store)
    runner.frame = lambda item, runtime: frames.get(item)  # type: ignore[method-assign]

    class _Strategy:
        def __init__(self, broker, config):
            self.broker = broker
            self.config = config

        async def init(self):
            return None

        async def on_bar(self, bar):
            if bar == _slot(27, 14, 30):
                await self.broker.buy_amount("000001.SZ", 10000)
            if bar == _slot(28, 10, 0):
                await self.broker.sell("000001.SZ", 100)

    class _Loader:
        @staticmethod
        def load_from_cache():
            return {"Dummy30m": _Strategy}

    monkeypatch.setattr("quantide.service.discovery.strategy_loader", _Loader())
    runtime = _runtime()

    for item in slots[:8]:
        assert runner.run(runtime, item) == 1
    run = store.get_run("paper:p1")
    assert run is not None and run["last_tracking_slot"] == bar_slot_text(_slot(27, 15, 0))
    bars = store.list_bars("paper:p1", "p1", bar_interval="30m")
    assert len(bars) == 8
    assert bars[-1]["trades"], "14:30 next_open intent should fill at 15:00"

    del frames[_slot(28, 11, 0)]
    assert runner.run(runtime, _slot(28, 10, 0)) == 1
    assert runner.run(runtime, _slot(28, 10, 30)) == 1
    assert runner.run(runtime, _slot(28, 11, 30)) == 0
    run = store.get_run("paper:p1")
    assert run is not None
    assert run["gap_slots"] == [bar_slot_text(_slot(28, 11, 0))]
    assert run["last_tracking_slot"] == bar_slot_text(_slot(28, 10, 30))
    day2 = [
        bar
        for bar in store.list_bars("paper:p1", "p1", bar_interval="30m")
        if str(bar["bar_slot"]).startswith("2026-10-28")
    ]
    assert len(day2) == 2
    assert day2[0]["positions"][0]["avail"] == day2[0]["positions"][0]["shares"]
    assert day2[0]["positions"][0]["avail"] > 0, "T+1 shares should unlock at day 2 open"
    assert day2[1]["trades"], "10:00 sell intent should fill at the next closed slot"
    assert day2[1]["positions"][0]["shares"] < day2[0]["positions"][0]["shares"]

    frames[_slot(28, 11, 0)] = _frame(_slot(28, 11, 0))
    assert runner.run(runtime, _slot(28, 13, 30)) == 3
    run = store.get_run("paper:p1")
    assert run is not None
    assert run["gap_slots"] == []
    assert run["last_tracking_slot"] == bar_slot_text(_slot(28, 13, 30))
    assert runner.run(runtime, _slot(28, 13, 30)) == 0

    day2 = [
        bar
        for bar in store.list_bars("paper:p1", "p1", bar_interval="30m")
        if str(bar["bar_slot"]).startswith("2026-10-28")
    ]
    assert len(day2) == 5
    assert len({bar["bar_slot"] for bar in day2}) == 5


def test_latest_closed_session_slot_rejects_lunch_and_post_close(monkeypatch):
    from quantide.service.shadow_intraday import latest_closed_session_slot
    from quantide.service.strategy_runtime import StrategyRuntimeManager

    monkeypatch.setattr(
        StrategyRuntimeManager,
        "_latest_completed_30m_bar",
        staticmethod(lambda now: now),
    )
    assert latest_closed_session_slot(_slot(27, 10, 0)) == _slot(27, 10, 0)
    assert latest_closed_session_slot(_slot(27, 13, 0)) is None
    assert latest_closed_session_slot(_slot(27, 15, 30)) is None
