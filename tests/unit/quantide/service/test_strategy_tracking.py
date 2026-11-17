"""dry-run tracking store / shadow broker 基础测试。"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from quantide.service.shadow_broker import ShadowBroker
from quantide.service.strategy_tracking import TrackingStore, bar_slot_text


def test_tracking_store_roundtrip(tmp_path):
    store = TrackingStore(tmp_path / "track.db")
    store.ensure_run(
        "paper:p1",
        "p1",
        start_date=datetime.date(2026, 10, 27),
        fill_timing="auction_close",
    )
    store.save_shadow_state("paper:p1", "p1", cash=100000, positions=[])
    store.save_daily(
        runtime_id="paper:p1",
        portfolio_id="p1",
        day=datetime.date(2026, 10, 27),
        source="dry_run",
        nav=100100,
        cash=90000,
        market_value=10100,
        positions=[{"asset": "000001.SZ", "shares": 100}],
        trades=[{"asset": "000001.SZ", "side": 1}],
        model_hash="m1",
    )
    store.save_daily(
        runtime_id="paper:p1",
        portfolio_id="p1",
        day=datetime.date(2026, 10, 27),
        source="actual",
        nav=100050,
        cash=90000,
        market_value=10050,
        positions=[],
    )
    rows = store.list_daily(runtime_id="paper:p1")
    assert len(rows) == 2
    assert {row["source"] for row in rows} == {"dry_run", "actual"}
    state = store.get_shadow_state("paper:p1")
    assert state is not None and state["cash"] == 100000


def test_shadow_broker_buy_and_sell_uses_backtest_close(monkeypatch):
    class _Bars:
        @staticmethod
        def get_bars_in_range(start, end=None, assets=None, adjust=None, eager_mode=True):
            return pl.DataFrame(
                {
                    "date": [datetime.date(2026, 10, 27)],
                    "asset": ["000001.SZ"],
                    "open": [10.0],
                    "high": [10.5],
                    "low": [9.8],
                    "close": [10.0],
                    "volume": [1000000.0],
                    "amount": [10_000_000.0],
                    "adjust": [1.0],
                    "is_st": [False],
                    "up_limit": [11.0],
                    "down_limit": [9.0],
                }
            )

    import quantide.service.shadow_broker as shadow_module

    monkeypatch.setattr(shadow_module, "daily_bars", _Bars())
    broker = ShadowBroker(
        portfolio_id="shadow",
        principal=100000,
        config={"commission": 1e-4, "stamp_duty": 5e-4, "transfer_fee": 1e-5, "min_commission": 5.0, "slippage_pct": 0.0},
        trade_date=datetime.date(2026, 10, 27),
    )
    broker.settle_t1()

    import asyncio

    result = asyncio.run(broker.buy_amount("000001.SZ", 10000))
    assert result.trades
    assert "000001.SZ" in broker.positions
    assert broker.positions["000001.SZ"].shares == 1000
    assert broker.trades[0]["price"] == pytest.approx(10.0)

    position = broker.positions["000001.SZ"]
    position.avail = position.shares
    sold = asyncio.run(broker.sell("000001.SZ", 500))
    assert sold.trades
    assert broker.positions["000001.SZ"].shares == 500


def test_intraday_bar_store_roundtrip_and_atomic_slot(tmp_path, monkeypatch):
    store = TrackingStore(tmp_path / "bar-track.db")
    monkeypatch.setattr("quantide.service.strategy_tracking.tracking_store", store)
    store.ensure_run(
        "paper:s1",
        "s1",
        start_date=datetime.date(2026, 10, 27),
        fill_timing="next_open",
        bar_interval="30m",
    )
    store.save_shadow_state("paper:s1", "s1", cash=100000, positions=[])
    slot = datetime.datetime(2026, 10, 27, 10, 0)
    intent = store.enqueue_next_open_intent(
        runtime_id="paper:s1:shadow",
        portfolio_id="s1",
        strategy_id="strategy-1:shadow",
        signal_date=slot.date(),
        target_date=slot.date(),
        method="buy",
        args=["000001.SZ", 100],
        kwargs={},
        intent_key="buy-1",
        signal_bar=slot - datetime.timedelta(minutes=30),
        target_bar=slot,
    )
    store.advance_intraday_slot(
        runtime_id="paper:s1",
        portfolio_id="s1",
        bar_slot="2026-10-27T10:00:00+08:00",
        bar_interval="30m",
        gap_slots=[],
        bars=[
            {
                "source": "dry_run",
                "nav": 100050,
                "cash": 99000,
                "market_value": 1050,
                "positions": [{"asset": "000001.SZ", "shares": 100}],
                "trades": [{"asset": "000001.SZ", "shares": 100}],
            }
        ],
        shadow_state={"cash": 99000, "positions": [{"asset": "000001.SZ", "shares": 100}]},
        processed_intent_ids=[intent["intent_id"]],
    )

    bars = store.list_bars("paper:s1", "s1", source="dry_run")
    assert len(bars) == 1
    assert bars[0]["bar_slot"] == "2026-10-27T10:00:00+08:00"
    assert bars[0]["trades"][0]["shares"] == 100
    run = store.get_run("paper:s1")
    assert run is not None
    assert run["bar_interval"] == "30m"
    assert run["last_tracking_slot"] == "2026-10-27T10:00:00+08:00"
    assert run["last_tracking_date"] == "2026-10-27"
    assert store.get_shadow_state("paper:s1")["last_bar_slot"] == "2026-10-27T10:00:00+08:00"
    assert store.list_next_open_intents(runtime_id="paper:s1:shadow") == []


def test_tracking_store_migrates_existing_daily_schema(tmp_path):
    import sqlite3

    path = tmp_path / "legacy-track.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE strategy_tracking_runs (
                runtime_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                backtest_id TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL DEFAULT '',
                fill_timing TEXT NOT NULL DEFAULT 'auction_close',
                dry_run_enabled INTEGER NOT NULL DEFAULT 1,
                last_tracking_date TEXT NOT NULL DEFAULT '',
                last_retrain_date TEXT NOT NULL DEFAULT '',
                gap_dates TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE strategy_tracking_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                runtime_id TEXT NOT NULL,
                portfolio_id TEXT NOT NULL,
                date TEXT NOT NULL,
                source TEXT NOT NULL,
                nav REAL NOT NULL DEFAULT 0,
                cash REAL NOT NULL DEFAULT 0,
                market_value REAL NOT NULL DEFAULT 0,
                positions TEXT NOT NULL DEFAULT '[]',
                trades TEXT NOT NULL DEFAULT '[]',
                model_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(runtime_id, date, source)
            );
            CREATE TABLE strategy_shadow_state (
                runtime_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                cash REAL NOT NULL,
                positions TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO strategy_tracking_runs
                (runtime_id, portfolio_id, updated_at)
                VALUES ('paper:old', 'old', '2026-10-27T00:00:00');
            INSERT INTO strategy_shadow_state
                (runtime_id, portfolio_id, cash, positions, updated_at)
                VALUES ('paper:old', 'old', 1234.0, '[]', '2026-10-27T00:00:00');
            """
        )
    store = TrackingStore(path)
    run = store.get_run("paper:old")
    assert run is not None
    assert run["bar_interval"] == "1d"
    assert run["last_tracking_slot"] == ""
    assert run["gap_slots"] == []
    assert store.get_shadow_state("paper:old")["last_bar_slot"] == ""
    store.save_bar(
        runtime_id="paper:old",
        portfolio_id="old",
        bar_slot="2026-10-27T10:00:00+08:00",
        bar_interval="30m",
        source="dry_run",
        nav=1235.0,
        cash=1234.0,
        market_value=1.0,
        positions=[],
    )
    assert len(store.list_bars("paper:old", "old")) == 1


def test_actual_snapshot_uses_durable_fills_and_is_write_once(tmp_path):
    import datetime
    from types import SimpleNamespace

    from quantide.service.strategy_session import StrategySession

    store = TrackingStore(tmp_path / "actual.db")
    runtime = SimpleNamespace(runtime_id="paper:actual", portfolio_id="actual")
    strategy = SimpleNamespace(_model_ref="Demo/model-artifact")
    slot = datetime.datetime(2026, 10, 27, 10, 0)
    first_fill = SimpleNamespace(
        tid="t1",
        tm=datetime.datetime(2026, 10, 27, 9, 59),
        to_dict=lambda: {"tid": "t1", "tm": "2026-10-27T09:59:00", "asset": "A"},
    )
    future_fill = SimpleNamespace(
        tid="t2",
        tm=datetime.datetime(2026, 10, 27, 10, 30),
        to_dict=lambda: {"tid": "t2", "tm": "2026-10-27T10:30:00", "asset": "A"},
    )
    broker = SimpleNamespace(
        asset=SimpleNamespace(total=9000.0, cash=9000.0, market_value=0.0),
        positions={},
        query_trades=lambda: [first_fill, future_fill],
    )
    session = object.__new__(StrategySession)
    session.manager = SimpleNamespace(tracking_store=store)
    session.runtime = runtime
    session.strategy = strategy
    session.broker = broker

    session._record_actual_bar(slot)
    saved = store.get_bar("paper:actual", bar_slot_text(slot), source="actual")
    assert saved is not None
    assert [trade["tid"] for trade in saved["trades"]] == ["t1"]
    assert saved["model_ref"] == "Demo/model-artifact"
    assert saved["model_hash"] == "model-artifact"

    broker.asset = SimpleNamespace(total=1.0, cash=1.0, market_value=0.0)
    broker.query_trades = lambda: [first_fill, future_fill]
    session._record_actual_bar(slot)
    unchanged = store.get_bar("paper:actual", bar_slot_text(slot), source="actual")
    assert unchanged is not None and unchanged["cash"] == 9000.0
    assert unchanged["created_at"] == saved["created_at"]


def test_new_session_does_not_repeat_same_closed_slot_callback(tmp_path):
    import asyncio
    import threading
    from types import SimpleNamespace

    from quantide.service.strategy_session import StrategySession

    slot = datetime.datetime(2024, 1, 2, 10, 0)
    store = TrackingStore(tmp_path / "restart.db")
    runtime = SimpleNamespace(runtime_id="paper:owned", portfolio_id="owned")
    manager = SimpleNamespace(
        tracking_store=store,
        _lock=threading.RLock(),
        _runtime_specs={},
        _latest_completed_30m_bar=lambda now: slot,
    )
    broker = SimpleNamespace(
        asset=SimpleNamespace(total=10000.0, cash=10000.0, market_value=0.0), positions={}
    )
    calls = []

    class Strategy:
        _model_ref = ""

        async def on_bar(self, tm):
            calls.append(tm.isoformat())

    def session():
        return StrategySession(manager, runtime, Strategy(), [], broker, "30m", "close", (None, None))

    asyncio.run(session()._minute_signal(slot))
    asyncio.run(session()._minute_signal(slot))

    assert calls == ["2024-01-02T10:00:00"]
    assert store.get_bar("paper:owned", bar_slot_text(slot), source="actual") is not None


def test_same_closed_bar_tick_still_advances_next_open_queue(tmp_path):
    import asyncio
    import threading
    from types import SimpleNamespace

    from quantide.service.strategy_session import StrategySession

    slot = datetime.datetime(2024, 1, 2, 10, 0)
    store = TrackingStore(tmp_path / "queue-tick.db")
    runtime = SimpleNamespace(runtime_id="paper:owned", portfolio_id="owned")
    calls: list[str] = []

    async def process(runtime_id, now):
        calls.append(now.isoformat())
        return 0

    manager = SimpleNamespace(
        tracking_store=store,
        _lock=threading.RLock(),
        _runtime_specs={},
        _latest_completed_30m_bar=lambda now: slot,
        process_next_open_30m_intents=process,
    )
    broker = SimpleNamespace(
        asset=SimpleNamespace(total=10000.0, cash=10000.0, market_value=0.0), positions={}
    )

    class Strategy:
        _model_ref = ""

        async def on_bar(self, tm):
            raise AssertionError("same bar callback must not repeat")

    session = StrategySession(
        manager, runtime, Strategy(), [], broker, "30m", "next_open", (None, None)
    )
    session.last_bar = slot
    asyncio.run(session._minute_signal(slot + datetime.timedelta(minutes=1)))

    assert calls == ["2024-01-02T10:01:00"]
