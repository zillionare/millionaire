"""Monthly aggregation, 3/12 signal and intent persistence tests."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.service.monthly_bars import (
    MonthlyBar,
    MonthlySeries,
    aggregate_monthly,
    monthly_ma_signals,
)
from quantide.service.monthly_intents import MonthlyIntentStore, intent_key
from quantide.strategies.example.monthly_ma import MonthlyMAStrategy


def _calendar(start: dt.date, months: int) -> list[dt.date]:
    days = []
    year, month = start.year, start.month
    for _ in range(months):
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1
        end = dt.date(next_year, next_month, 1) - dt.timedelta(days=1)
        while end.weekday() >= 5:
            end -= dt.timedelta(days=1)
        days.extend([end - dt.timedelta(days=1), end])
        year, month = next_year, next_month
    return days


def _daily(calendar, asset="A", skip_end=False):
    rows = []
    for day in calendar:
        if skip_end and day == max(item for item in calendar if item.month == day.month):
            continue
        rows.append(
            {
                "date": day,
                "asset": asset,
                "open": 10.0 + day.month,
                "high": 12.0 + day.month,
                "low": 9.0 + day.month,
                "close": 11.0 + day.month,
                "volume": 100.0,
                "amount": 1100.0,
            }
        )
    return pl.DataFrame(rows)


def test_monthly_ohlcv_uses_actual_month_end_and_splits_forming() -> None:
    calendar = _calendar(dt.date(2024, 1, 1), 3)
    panel = _daily(calendar)
    as_of = min(day for day in calendar if day.month == 3)
    series = aggregate_monthly(panel, calendar, as_of=as_of)["A"]
    assert len(series.closed) == 2
    assert len(series.forming) == 1
    january = series.closed[0]
    assert january.end_date == max(day for day in calendar if day.month == 1)
    assert january.start_date == min(day for day in calendar if day.month == 1)
    assert january.volume == 200
    assert january.available_at.hour == 15
    assert series.forming[0].end_date <= as_of


def test_missing_month_end_is_incomplete_not_fabricated() -> None:
    calendar = _calendar(dt.date(2024, 1, 1), 2)
    panel = _daily(calendar, skip_end=True)
    series = aggregate_monthly(panel, calendar, as_of=calendar[-1])["A"]
    assert not series.closed
    assert series.incomplete
    assert "missing month-end" in series.diagnostics[0]


def _bar(month: int, close: float, end: dt.date, asset="A") -> MonthlyBar:
    return MonthlyBar(
        asset,
        dt.date(2023, month, 1),
        end - dt.timedelta(days=1),
        end,
        close,
        close,
        close,
        close,
        1,
        1,
        True,
        dt.datetime.combine(end, dt.time(15)),
        1,
    )


def test_cross_requires_thirteen_closed_months_and_executes_next_day() -> None:
    start = dt.date(2023, 1, 1)
    ends = []
    for index in range(15):
        month = start.month + index
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        ends.append(dt.date(year, month, 28))
    closes = [12 - index for index in range(12)] + [20, 25, 26]
    bars = tuple(_bar(end.month, close, end) for end, close in zip(ends, closes, strict=True))
    series = MonthlySeries("A", bars)
    calendar = tuple(sorted([*ends, dt.date(2024, 1, 29), dt.date(2024, 4, 1)]))
    assert monthly_ma_signals(MonthlySeries("A", bars[:12]), calendar) == []
    signals = monthly_ma_signals(series, calendar)
    assert signals
    assert signals[-1].direction == "buy"
    assert signals[-1].execute_date == dt.date(2024, 1, 29)


def test_strategy_defaults_to_a_tradable_stock_asset() -> None:
    class _Broker:
        portfolio_id = "p"

        @property
        def positions(self):
            return {}

    strategy = MonthlyMAStrategy(_Broker(), {})

    assert strategy.asset == "000001.SZ"


def test_strategy_rejects_interval_override_and_fixed_windows() -> None:
    class _Broker:
        portfolio_id = "p"

        @property
        def positions(self):
            return {}

    with pytest.raises(ValueError, match="1M"):
        MonthlyMAStrategy(_Broker(), {"bar_interval": "1d"})
    with pytest.raises(ValueError, match="3/12"):
        MonthlyMAStrategy(_Broker(), {"short_window": 5})
    strategy = MonthlyMAStrategy(_Broker(), {})
    assert strategy.BAR_INTERVAL == "1M"


def test_monthly_intents_are_idempotent_and_persisted(tmp_path) -> None:
    store = MonthlyIntentStore(tmp_path / "intents.json")
    intent = {"key": "A:2024-01-31:buy", "asset": "A", "direction": "buy"}
    assert store.enqueue(intent)
    assert not store.enqueue(intent)
    assert store.seen(intent["key"])
    assert len(store.pending()) == 1
    store.complete(intent["key"])
    assert store.pending() == []
    assert MonthlyIntentStore(tmp_path / "intents.json").seen(intent["key"])


def test_runner_preserves_monthly_interval_and_rejects_daily_override() -> None:
    from quantide.core.enums import FrameType
    from quantide.service.runner import BacktestRunner

    assert BacktestRunner.strategy_interval(MonthlyMAStrategy) == "1M"
    assert BacktestRunner.validate_strategy_interval(MonthlyMAStrategy, {}, FrameType.MONTH) == "1M"
    with pytest.raises(ValueError, match="1M"):
        BacktestRunner.validate_strategy_interval(MonthlyMAStrategy, {}, FrameType.DAY)
    with pytest.raises(ValueError, match="bar_interval"):
        BacktestRunner.validate_strategy_interval(
            MonthlyMAStrategy, {"bar_interval": "1d"}, FrameType.MONTH
        )
    with pytest.raises(ValueError, match="1m"):
        BacktestRunner.validate_strategy_interval(
            MonthlyMAStrategy, {"bar_interval": "1m"}, FrameType.MONTH
        )


def test_runner_does_not_confuse_month_and_minute_tokens() -> None:
    from quantide.core.enums import FrameType
    from quantide.service.runner import BacktestRunner

    class _MinuteStrategy:
        BAR_INTERVAL = "1m"

        @staticmethod
        def default_config() -> dict:
            return {}

    with pytest.raises(ValueError, match="1m"):
        BacktestRunner.strategy_interval(_MinuteStrategy)

    class _MonthlyStrategy:
        BAR_INTERVAL = "1M"

        @staticmethod
        def default_config() -> dict:
            return {}

    assert BacktestRunner.validate_strategy_interval(_MonthlyStrategy, {}, FrameType.MONTH) == "1M"


@pytest.mark.asyncio
async def test_strategy_defers_to_next_session_and_recovery_is_idempotent(tmp_path) -> None:
    ends = []
    for index in range(15):
        month = index + 1
        year = 2023 + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = dt.date(year, month, 28)
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
        ends.append(day)
    signal_day = ends[12]
    execute_day = dt.date(2024, 2, 1)
    calendar_days = sorted({*ends, execute_day})
    closes = [100.0] * 12 + [120.0, 130.0, 140.0]
    panel = pl.DataFrame(
        [
            {
                "date": day,
                "asset": "A",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "amount": close,
            }
            for day, close in zip(ends, closes, strict=True)
        ]
    )

    class FakeCalendar:
        @staticmethod
        def get_trade_dates(start, end):
            return [day for day in calendar_days if start <= day <= end]

        @staticmethod
        def day_shift(day, count):
            return day + dt.timedelta(days=count)

    class Broker:
        def __init__(self):
            self.positions = {}
            self.calls = []

        async def buy_amount(self, asset, amount, price=0, order_time=None):
            self.calls.append((asset, amount, price, order_time))
            return type("Result", (), {"qt_oid": f"oid-{len(self.calls)}"})()

        async def sell(self, asset, shares, price=0, order_time=None):
            self.calls.append((asset, shares, price, order_time))
            return type("Result", (), {"qt_oid": f"oid-{len(self.calls)}"})()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setitem(MonthlyMAStrategy.on_bar.__globals__, "calendar", FakeCalendar)
    try:
        store = MonthlyIntentStore(tmp_path / "intents.json")
        broker = Broker()
        strategy = MonthlyMAStrategy(
            broker,
            {"signal_asset": "A", "invest_amount": 1000},
            store=store,
            history_loader=lambda day: panel if day == signal_day else pl.DataFrame(),
        )
        await strategy.on_bar(dt.datetime.combine(signal_day, dt.time(15)))
        assert broker.calls == []
        assert len(store.pending()) == 1
        assert store.seen(intent_key(strategy.namespace, "A", signal_day, "buy"))

        await strategy.on_bar(dt.datetime.combine(execute_day, dt.time(9, 30)))
        assert len(broker.calls) == 1
        assert broker.calls[0][0:2] == ("A", 1000)
        assert broker.calls[0][3].date() == execute_day
        assert broker.calls[0][3].time() == dt.time(9, 30)
        assert store.pending() == []

        crash_key = "A:2024-01-26:crash"
        store.enqueue(
            {
                "key": crash_key,
                "namespace": strategy.namespace,
                "asset": "A",
                "signal_date": "2024-01-25",
                "execute_date": execute_day.isoformat(),
                "direction": "buy",
                "amount": 500,
            }
        )
        await strategy.on_bar(dt.datetime.combine(execute_day, dt.time(9, 30)))
        assert len(broker.calls) == 2
        assert store.pending() == []
        recovered = MonthlyMAStrategy(
            broker,
            {"signal_asset": "A", "invest_amount": 1000},
            store=MonthlyIntentStore(tmp_path / "intents.json"),
            history_loader=lambda day: pl.DataFrame(),
        )
        await recovered.on_bar(dt.datetime.combine(execute_day, dt.time(9, 30)))
        assert len(broker.calls) == 2
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_sell_intent_without_position_is_completed(tmp_path) -> None:
    class _Broker:
        portfolio_id = "p"
        positions: dict[str, object] = {}

    store = MonthlyIntentStore(tmp_path / "intents.json")
    strategy = MonthlyMAStrategy(_Broker(), {"signal_asset": "A"}, store=store)
    intent = {
        "key": "stale-sell",
        "asset": "A",
        "direction": "sell",
        "execute_date": "2024-01-02",
    }
    store.enqueue(intent)

    await strategy._submit(intent, dt.date(2024, 1, 2))

    assert store.pending() == []


def test_monthly_history_uses_future_calendar_to_keep_midmonth_forming(monkeypatch) -> None:
    from quantide.data.models.daily_bars import daily_bars
    from quantide.service.monthly_bars import monthly_history

    days = [dt.date(2024, 9, 2), dt.date(2024, 9, 13), dt.date(2024, 9, 30)]
    panel = pl.DataFrame(
        [
            {
                "date": day,
                "asset": "A",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1.0,
                "amount": 10.0,
            }
            for day in days[:2]
        ]
    )
    monkeypatch.setattr(daily_bars, "get_bars_in_range", lambda *args, **kwargs: panel)
    history = monthly_history("A", 3, days[1], days, include_forming=True)
    assert len(history) == 1
    row = history.row(0, named=True)
    assert row["date"] == days[1]
    assert row["closed"] is False


@pytest.mark.asyncio
async def test_monthly_intents_are_namespaced_per_account(tmp_path) -> None:
    ends = []
    for index in range(13):
        month = index + 1
        year = 2023 + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = dt.date(year, month, 28)
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
        ends.append(day)
    execute_day = dt.date(2024, 2, 1)
    days = sorted({*ends, execute_day})
    closes = [100.0] * 12 + [120.0]
    panel = pl.DataFrame(
        [
            {
                "date": day,
                "asset": "A",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "amount": close,
            }
            for day, close in zip(ends, closes, strict=True)
        ]
    )
    store = MonthlyIntentStore(tmp_path / "intents.json")

    class FakeCalendar:
        @staticmethod
        def get_trade_dates(start, end):
            return [day for day in days if start <= day <= end]

        @staticmethod
        def day_shift(day, count):
            return day + dt.timedelta(days=count)

    class Broker:
        def __init__(self, portfolio_id):
            self.portfolio_id = portfolio_id
            self.kind = type("Kind", (), {"value": "bt"})()
            self.positions = {}
            self.calls = []

        async def buy_amount(self, asset, amount, price=0, order_time=None):
            self.calls.append(asset)
            return type("Result", (), {"qt_oid": f"{self.portfolio_id}-{len(self.calls)}"})()

    first = Broker("one")
    second = Broker("two")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setitem(MonthlyMAStrategy.on_bar.__globals__, "calendar", FakeCalendar)
    try:
        for broker in (first, second):
            strategy = MonthlyMAStrategy(
                broker,
                {"signal_asset": "A", "invest_amount": 1000},
                store=store,
                history_loader=lambda day: panel if day == ends[-1] else pl.DataFrame(),
            )
            await strategy.on_bar(dt.datetime.combine(ends[-1], dt.time(15)))
        assert first.calls == []
        assert second.calls == []
        for broker in (first, second):
            strategy = MonthlyMAStrategy(
                broker,
                {"signal_asset": "A", "invest_amount": 1000},
                store=store,
                history_loader=lambda day: pl.DataFrame(),
            )
            await strategy.on_bar(dt.datetime.combine(execute_day, dt.time(9, 30)))
        assert first.calls == ["A"]
        assert second.calls == ["A"]
        completed = store._read()["completed"]
        assert len(completed) == 2
        assert len({item["namespace"] for item in completed.values()}) == 2
        assert len({item["order_id"] for item in completed.values()}) == 2
    finally:
        monkeypatch.undo()
