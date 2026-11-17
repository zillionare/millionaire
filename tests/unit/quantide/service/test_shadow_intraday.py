"""Closed-bar 30m Shadow-Run replay, gaps, T+1 and restart idempotency."""

from __future__ import annotations

import datetime
from pathlib import Path
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


def test_latest_closed_session_slot_falls_back_to_closed_session(monkeypatch):
    from quantide.service.shadow_intraday import latest_closed_session_slot
    from quantide.service.strategy_runtime import StrategyRuntimeManager

    monkeypatch.setattr(
        StrategyRuntimeManager,
        "_latest_completed_30m_bar",
        staticmethod(lambda now: now),
    )
    assert latest_closed_session_slot(_slot(27, 10, 0)) == _slot(27, 10, 0)
    from quantide.service.shadow_intraday import SESSION_SLOT_TIMES

    for now in (_slot(27, 13, 0), _slot(27, 15, 30)):
        closed = latest_closed_session_slot(now)
        assert closed is None or (closed <= now and closed.time() in SESSION_SLOT_TIMES)


def test_first_slot_at_or_after_keeps_exact_enable_boundary(monkeypatch):
    from quantide.service import shadow_intraday as module

    monkeypatch.setattr(module.calendar, "is_trade_day", lambda _: True)
    assert module.first_slot_at_or_after(_slot(27, 10, 15)) == _slot(27, 10, 30)
    assert module.first_slot_at_or_after(_slot(27, 9, 0)) == _slot(27, 10, 0)


def test_shadow_actual_bar_uses_persisted_fact_not_current_broker(tmp_path, monkeypatch):
    store = TrackingStore(tmp_path / "shadow-actual.db")
    slot = _slot(27, 10, 0)
    store.ensure_run(
        "paper:p1", "p1", start_date=slot.date(), bar_interval="30m", start_slot=bar_slot_text(slot)
    )
    store.save_bar(
        runtime_id="paper:p1",
        portfolio_id="p1",
        bar_slot=bar_slot_text(slot),
        bar_interval="30m",
        source="actual",
        nav=8000.0,
        cash=8000.0,
        market_value=0.0,
        positions=[],
        trades=[{"asset": "000001.SZ", "amount": 100.0}],
        model_hash="old-model",
    )
    runtime = _runtime()
    runtime.broker = SimpleNamespace(
        asset=SimpleNamespace(total=9000.0, cash=9000.0, market_value=0.0), positions={}
    )
    runner = IntradayShadowRunner(store)
    runner.frame = lambda item, runtime: _frame(item)  # type: ignore[method-assign]
    calls = []

    def _replay(self, runtime, bar_slot, frame):
        calls.append(bar_slot)
        return {
            "dry_run": {
                "source": "dry_run",
                "nav": 10000.0,
                "cash": 10000.0,
                "market_value": 0.0,
                "positions": [],
                "trades": [],
                "model_hash": "",
            },
            "shadow_state": {"cash": 10000.0, "positions": []},
            "processed_intent_ids": [],
        }

    monkeypatch.setattr(IntradayShadowRunner, "_replay", _replay)
    monkeypatch.setattr(
        "quantide.service.shadow_intraday.latest_closed_session_slot", lambda now=None: slot
    )
    monkeypatch.setattr(
        "quantide.service.shadow_intraday.next_session_slot",
        lambda item: item + datetime.timedelta(minutes=30),
    )

    assert runner.run(runtime) == 1
    actual = store.get_bar("paper:p1", bar_slot_text(slot), source="actual")
    assert actual is not None
    assert actual["cash"] == 8000.0
    assert actual["model_hash"] == "old-model"


def test_real_subprocess_kill_after_committed_bar_resumes_without_duplicate(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    import textwrap

    root = tmp_path / "crash"
    root.mkdir()
    database = root / "shadow.db"
    marker = root / "killed.marker"
    script = root / "child.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import datetime, os, signal
            import polars as pl
            from types import SimpleNamespace
            from quantide.service.shadow_intraday import IntradayShadowRunner
            from quantide.service.strategy_tracking import TrackingStore, bar_slot_text

            slot = datetime.datetime(2026, 10, 27, 10, 0)
            end = datetime.datetime(2026, 10, 27, 10, 30)
            store = TrackingStore(r\"{database}\")
            store.ensure_run("paper:crash", "crash", start_date=slot.date(), bar_interval="30m", start_slot=bar_slot_text(slot))
            runtime = SimpleNamespace(runtime_id="paper:crash", portfolio_id="crash", interval="30m", config={{}}, principal=10000.0)

            class Runner(IntradayShadowRunner):
                def frame(self, item, runtime):
                    return pl.DataFrame({{"asset": ["A"], "close": [10.0]}})
                def _replay(self, runtime, item, frame):
                    if item == end and not os.path.exists(r\"{marker}\"):
                        open(r\"{marker}\", "w").close()
                        os.kill(os.getpid(), signal.SIGKILL)
                    return {{"dry_run": {{"source": "dry_run", "nav": 10000.0, "cash": 10000.0, "market_value": 0.0, "positions": [], "trades": [], "model_hash": ""}}, "shadow_state": {{"cash": 10000.0, "positions": []}}, "processed_intent_ids": []}}

            import quantide.service.shadow_intraday as module
            module.latest_closed_session_slot = lambda now=None: end
            module.next_session_slot = lambda item: item + datetime.timedelta(minutes=30)
            Runner(store).run(runtime)
            """
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=Path(__file__).parents[4],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert marker.exists()
    store = TrackingStore(database)
    first = store.get_bar("paper:crash", bar_slot_text(_slot(27, 10, 0)), source="dry_run")
    assert first is not None
    assert store.get_run("paper:crash")["last_tracking_slot"] == bar_slot_text(_slot(27, 10, 0))

    class Runner(IntradayShadowRunner):
        def frame(self, item, runtime):
            return pl.DataFrame({"asset": ["A"], "close": [10.0]})

        def _replay(self, runtime, item, frame):
            return {
                "dry_run": {
                    "source": "dry_run",
                    "nav": 10000.0,
                    "cash": 10000.0,
                    "market_value": 0.0,
                    "positions": [],
                    "trades": [],
                    "model_hash": "",
                },
                "shadow_state": {"cash": 10000.0, "positions": []},
                "processed_intent_ids": [],
            }

    from quantide.service import shadow_intraday as module

    monkeypatch.setattr(module, "latest_closed_session_slot", lambda now=None: _slot(27, 10, 30))
    monkeypatch.setattr(
        module, "next_session_slot", lambda item: item + datetime.timedelta(minutes=30)
    )
    runner = Runner(store)
    runtime = _runtime()
    runtime.runtime_id = "paper:crash"
    runtime.portfolio_id = "crash"
    assert runner.run(runtime) == 1
    assert store.get_bar("paper:crash", bar_slot_text(_slot(27, 10, 30)), source="dry_run")
    assert runner.run(runtime) == 0


def test_anchor_never_invents_weekday_slots_without_authoritative_calendar(monkeypatch):
    from quantide.service import shadow_intraday as module

    monkeypatch.setattr(module.calendar, "is_trade_day", lambda _day: False)

    assert module.first_slot_at_or_after(_slot(27, 10, 15)) is None
