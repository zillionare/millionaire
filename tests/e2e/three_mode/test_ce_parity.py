"""CE parity over actual HTTP, using independently calculated account results."""

import datetime
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import polars as pl
import pytest

from quantide.config.settings import get_timezone
from quantide.core.enums import FrameType
from quantide.core.order_identity import client_order_id
from quantide.core.runtime.simulated_broker import SimulatedBrokerAdapter
from quantide.core.strategy import BaseStrategy
from quantide.data.models.calendar import calendar
from quantide.data.sqlite import db
from quantide.service.backtest_broker import BacktestBroker
from quantide.service.sim_broker import PaperBroker

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]
START = datetime.datetime(2024, 1, 2, 10, tzinfo=get_timezone())
SYMBOL = "000001.SZ"


class ScheduleStrategy(BaseStrategy):
    async def on_bar(self, tm):
        index = (tm.date() - START.date()).days
        if index == 0:
            await self.broker.buy(SYMBOL, 200, price=10, order_time=tm, timeout=0.001)
        else:
            await self.broker.sell(SYMBOL, 100, price=10 + index, order_time=tm, timeout=0.001)


class Feed:
    def __init__(self):
        self.frame = pl.DataFrame(
            [
                {
                    "date": START.date() + datetime.timedelta(days=index),
                    "asset": SYMBOL,
                    "open": 10.0 + index,
                    "close": 10.0 + index,
                    "high": 10.0 + index,
                    "low": 10.0 + index,
                    "volume": 10000.0,
                    "amount": 100000.0,
                    "adjust": 1.0,
                    "is_st": False,
                    "up_limit": 99.0,
                    "down_limit": 1.0,
                }
                for index in range(3)
            ]
        )

    def get_price_for_match(self, asset, tm):
        return self.frame.filter((pl.col("asset") == asset) & (pl.col("date") == tm.date()))

    def get_trade_price_limits(self, asset, day):
        return 1.0, 10.0

    def get_bars(self, n, end=None, assets=None, **kwargs):
        return self.frame.filter(pl.col("date") <= end).tail(n)

    def get_bars_in_range(self, start, end=None, assets=None, **kwargs):
        return self.frame.filter(pl.col("date").is_between(start, end or start))

    def get_close_adjust_factor(self, assets, start, end):
        return self.get_bars_in_range(start, end).select("date", "asset", "close", "adjust")


@pytest.fixture
def counter_server(tmp_path):
    processes = []

    def start(**settings):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        database = tmp_path / "counter.db"
        source = (
            "import uvicorn; from quantide.service.simulated_counter_api import create_counter_app; "
            f"uvicorn.run(create_counter_app({str(database)!r}, **{settings!r}), host='127.0.0.1', port={port}, "
            "log_level='error')"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", source], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        processes.append(process)
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with httpx.Client(trust_env=False, timeout=0.2) as client:
                    client.get(url + "/state").raise_for_status()
                return process, url
            except httpx.HTTPError:
                assert process.poll() is None, "counter exited during startup"
                time.sleep(0.02)
        raise AssertionError("counter did not start")

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "commission,stamp_tax,expected_cash",
    [
        (0.0, 0.0, [8000.0, 9100.0, 10300.0]),
        (0.001, 0.001, [7998.0, 9095.8, 10293.4]),
    ],
)
async def test_three_modes_match_manual_account_facts(
    tmp_path, counter_server, commission, stamp_tax, expected_cash
):
    calendar.load(Path(__file__).parents[2] / "assets" / "baseline_calendar.parquet")
    db.init(tmp_path / "app.db")
    _, url = counter_server(commission=commission, stamp_tax=stamp_tax)
    remote = SimulatedBrokerAdapter(url)
    paper = PaperBroker.create(
        "parity-paper",
        principal=10000,
        commission=commission,
        stamp_tax=stamp_tax,
        min_commission=0,
        clock=type("Clock", (), {"now": lambda self: START})(),
    )
    backtest = BacktestBroker(
        START.date(),
        START.date() + datetime.timedelta(days=2),
        "parity-backtest",
        Feed(),
        principal=10000,
        commission=commission,
        stamp_duty=stamp_tax,
        transfer_fee=0,
        min_commission=0,
    )
    strategies = [ScheduleStrategy(broker, {}) for broker in (backtest, paper, remote)]
    try:
        for index in range(3):
            tm = START + datetime.timedelta(days=index)
            backtest.set_clock(tm.replace(tzinfo=get_timezone()))
            paper.set_clock(tm)
            paper.settle_t1()
            remote.on_quote(tm, {SYMBOL: {"price": 10 + index}})
            for strategy in strategies:
                await strategy.on_bar(tm)
            paper.on_quote({SYMBOL: {"price": 10 + index}})
            cash = expected_cash[index]
            expected_shares = [200, 100, 0][index]
            for broker in (backtest, paper):
                assert broker.cash == pytest.approx(cash)
                positions = broker.positions
                if isinstance(positions, dict):
                    positions = positions.values()
                assert sum(position.shares for position in positions) == expected_shares
            assert remote.query_assets().cash == pytest.approx(cash)
            assert sum(position.shares for position in remote.query_positions()) == expected_shares
            assert remote.query_assets().total == pytest.approx(
                cash + expected_shares * (10 + index)
            )
        expected_fees = [
            2000 * commission,
            1100 * (commission + stamp_tax),
            1200 * (commission + stamp_tax),
        ]
        for portfolio in ("parity-paper", "parity-backtest"):
            trades = db.trades_all(portfolio_id=portfolio).sort("tm")
            assert trades["shares"].to_list() == [200, 100, 100]
            assert trades["price"].to_list() == [10, 11, 12]
            assert trades["fee"].to_list() == pytest.approx(expected_fees)
        assert [trade.shares for trade in remote.query_trades()] == [200, 100, 100]
        assert [trade.fee for trade in remote.query_trades()] == pytest.approx(expected_fees)
    finally:
        paper.close()
        remote.close()
        db.close()


@pytest.mark.asyncio
async def test_counter_duplicate_partial_cancel_and_abrupt_restart(counter_server):
    process, url = counter_server()
    broker = SimulatedBrokerAdapter(url)
    broker.on_quote(START, {SYMBOL: {"price": 10, "available_shares": 100}})
    token = client_order_id.set("durable-intent")
    try:
        await broker.buy(SYMBOL, 200, price=10, order_time=START)
        await broker.buy(SYMBOL, 200, price=10, order_time=START)
    finally:
        client_order_id.reset(token)
    assert broker.query_assets().cash == 9000
    assert len(broker.query_trades()) == 1
    process.kill()
    process.wait(timeout=10)
    broker.close()
    _, restarted_url = counter_server()
    broker = SimulatedBrokerAdapter(restarted_url)
    try:
        assert broker.find_order_by_client_id("durable-intent")["filled"] == 100
        await broker.cancel("durable-intent")
        broker.on_quote(START + datetime.timedelta(days=1), {SYMBOL: {"price": 11}})
        assert len(broker.query_trades()) == 1
        assert broker.query_positions()[0].avail == 100
        assert broker.query_assets().total == 10100
    finally:
        broker.close()


@pytest.mark.asyncio
async def test_counter_bulk_cancel_accepts_strategy_order_side_enum(counter_server):
    from quantide.core.enums import OrderSide

    _, url = counter_server()
    broker = SimulatedBrokerAdapter(url)
    try:
        await broker.buy(SYMBOL, 100, price=9, order_time=START)
        await broker.buy(SYMBOL, 100, price=8, order_time=START)
        assert len(broker.query_orders("open")) == 2
        assert await broker.cancel_all_orders(OrderSide.SELL) == 0
        assert await broker.cancel_all_orders(OrderSide.BUY) == 2
        assert broker.query_orders("open") == []
        assert len(broker.query_orders("cancelled")) == 2
    finally:
        broker.close()


@pytest.mark.asyncio
async def test_monthly_intents_replay_consistently_across_three_paths(tmp_path, counter_server):
    from quantide.service.monthly_intents import MonthlyIntentStore, execute_intent

    calendar.load(Path(__file__).parents[2] / "assets" / "baseline_calendar.parquet")
    db.init(tmp_path / "app.db")
    _, url = counter_server(commission=0.0, stamp_tax=0.0)
    remote = SimulatedBrokerAdapter(url)
    paper = PaperBroker.create(
        "monthly-paper",
        principal=10000,
        commission=0.0,
        stamp_tax=0.0,
        min_commission=0,
        clock=type("Clock", (), {"now": lambda self: START})(),
    )
    backtest = BacktestBroker(
        START.date(),
        START.date() + datetime.timedelta(days=2),
        "monthly-backtest",
        Feed(),
        principal=10000,
        commission=0.0,
        stamp_duty=0.0,
        transfer_fee=0,
        min_commission=0,
    )
    paths = [
        ("backtest", backtest, MonthlyIntentStore(tmp_path / "backtest-intents.json")),
        ("paper", paper, MonthlyIntentStore(tmp_path / "paper-intents.json")),
        ("counter", remote, MonthlyIntentStore(tmp_path / "counter-intents.json")),
    ]
    buy_day = START.date()
    sell_day = buy_day + datetime.timedelta(days=2)
    buy = {
        "key": "000001.SZ:2024-01-31:buy",
        "asset": SYMBOL,
        "signal_date": "2024-01-31",
        "execute_date": buy_day.isoformat(),
        "direction": "buy",
        "amount": 10000.0,
        "price": 10.0,
    }
    sell = {
        "key": "000001.SZ:2024-02-29:sell",
        "asset": SYMBOL,
        "signal_date": "2024-02-29",
        "execute_date": sell_day.isoformat(),
        "direction": "sell",
        "shares": 1000.0,
        "price": 12.0,
    }
    for _, _, store in paths:
        assert store.enqueue(buy)
        assert store.enqueue(sell)
    try:
        for index in range(3):
            tm = START + datetime.timedelta(days=index)
            backtest.set_clock(tm.replace(tzinfo=get_timezone()))
            paper.set_clock(tm)
            paper.settle_t1()
            remote.on_quote(tm, {SYMBOL: {"price": 10 + index}})
            for _, broker, store in paths:
                for intent in store.due(tm.date()):
                    await execute_intent(
                        broker,
                        intent,
                        order_time=tm,
                    )
                    store.complete(str(intent["key"]))
            paper.on_quote({SYMBOL: {"price": 10 + index}})
        expected_cash = 12000.0
        expected_shares = [0, 0, 0]
        for index, (_, broker, _) in enumerate(paths[:2]):
            assert broker.cash == pytest.approx(expected_cash)
            positions = broker.positions
            if isinstance(positions, dict):
                positions = positions.values()
            assert sum(position.shares for position in positions) == expected_shares[index]
        assert remote.query_assets().cash == pytest.approx(expected_cash)
        assert remote.query_positions() == []
        for _, _, store in paths:
            assert store.pending() == []
            assert MonthlyIntentStore(store.path).pending() == []
        for portfolio in ("monthly-paper", "monthly-backtest"):
            trades = db.trades_all(portfolio_id=portfolio).sort("tm")
            assert trades["shares"].to_list() == [1000, 1000]
            assert trades["price"].to_list() == [10, 12]
        assert [trade.shares for trade in remote.query_trades()] == [1000, 1000]
        assert [trade.price for trade in remote.query_trades()] == [10, 12]
    finally:
        paper.close()
        remote.close()
        db.close()


@pytest.mark.asyncio
async def test_counter_defers_next_session_order_until_its_date(counter_server):
    _, url = counter_server()
    broker = SimulatedBrokerAdapter(url)
    broker.on_quote(START, {SYMBOL: {"price": 10}})
    token = client_order_id.set("monthly-next-open")
    try:
        await broker.buy(
            SYMBOL,
            100,
            price=0,
            order_time=START + datetime.timedelta(days=2),
        )
        assert broker.query_trades() == []
        assert broker.query_assets().cash == 10000
        broker.on_quote(START + datetime.timedelta(days=1), {SYMBOL: {"price": 11}})
        assert broker.query_trades() == []
        broker.on_quote(START + datetime.timedelta(days=2), {SYMBOL: {"price": 12}})
        trades = broker.query_trades()
        assert [trade.price for trade in trades] == [12]
        assert broker.query_assets().cash == 8800
    finally:
        client_order_id.reset(token)
        broker.close()


class MonthlyFeed:
    def __init__(self, signal_day, execution_day):
        self.frame = pl.DataFrame(
            [
                {
                    "date": day,
                    "asset": SYMBOL,
                    "open": 9.99,
                    "close": 9.99,
                    "high": 9.99,
                    "low": 9.99,
                    "volume": 10000.0,
                    "amount": 99900.0,
                    "adjust": 1.0,
                    "is_st": False,
                    "up_limit": 10.0,
                    "down_limit": 1.0,
                }
                for day in (signal_day, execution_day)
            ]
        )

    def get_price_for_match(self, asset, tm):
        return self.frame.filter((pl.col("asset") == asset) & (pl.col("date") == tm.date()))

    def get_trade_price_limits(self, asset, day):
        return 1.0, 10.0

    def get_bars(self, n, end=None, assets=None, **kwargs):
        return self.frame.filter(pl.col("date") <= end).tail(n)

    def get_bars_in_range(self, start, end=None, assets=None, **kwargs):
        return self.frame.filter(pl.col("date").is_between(start, end or start))

    def get_close_adjust_factor(self, assets, start, end):
        return self.get_bars_in_range(start, end).select("date", "asset", "close", "adjust")


class MonthlyMarketData:
    def snapshot(self, assets):
        return {
            asset: type(
                "Snap",
                (),
                {
                    "price": 9.99,
                    "open": 9.99,
                    "high": 9.99,
                    "low": 9.99,
                    "volume": 10000.0,
                    "amount": 99900.0,
                },
            )()
            for asset in assets
        }


def _monthly_days() -> tuple[list[datetime.date], datetime.date]:
    days = list(calendar.get_trade_dates(datetime.date(2023, 1, 1), datetime.date(2024, 1, 31)))
    months: dict[tuple[int, int], datetime.date] = {}
    for day in days:
        months[(day.year, day.month)] = day
    ends = [months[key] for key in sorted(months)]
    return ends[-13:], calendar.day_shift(ends[-1], 1)


@pytest.mark.asyncio
async def test_real_monthly_strategy_runs_across_three_brokers(tmp_path, counter_server):
    from quantide.service.monthly_intents import MonthlyIntentStore
    from quantide.strategies.example.monthly_ma import MonthlyMAStrategy

    calendar.load(Path(__file__).parents[2] / "assets" / "baseline_calendar.parquet")
    db.init(tmp_path / "app.db")
    month_ends, execution_day = _monthly_days()
    signal_day = month_ends[-1]
    panel = pl.DataFrame(
        [
            {
                "date": day,
                "asset": SYMBOL,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "amount": close,
            }
            for day, close in zip(month_ends, [100.0] * 12 + [120.0], strict=True)
        ]
    )
    _, url = counter_server(commission=0.0, stamp_tax=0.0)
    remote = SimulatedBrokerAdapter(url, portfolio_id="real-monthly-paper")
    paper = PaperBroker.create(
        "real-monthly-paper",
        principal=10000,
        commission=0.0,
        stamp_tax=0.0,
        min_commission=0,
        market_data=MonthlyMarketData(),
        clock=type(
            "Clock",
            (),
            {
                "now": lambda self: datetime.datetime.combine(
                    signal_day, datetime.time(15), tzinfo=get_timezone()
                )
            },
        )(),
    )
    backtest = BacktestBroker(
        signal_day,
        execution_day,
        "real-monthly-backtest",
        MonthlyFeed(signal_day, execution_day),
        principal=10000,
        commission=0.0,
        stamp_duty=0.0,
        transfer_fee=0,
        min_commission=0,
    )
    paths = [
        ("backtest", backtest, MonthlyIntentStore(tmp_path / "bt-intents.json")),
        ("paper", paper, MonthlyIntentStore(tmp_path / "paper-intents.json")),
        ("counter", remote, MonthlyIntentStore(tmp_path / "counter-intents.json")),
    ]
    strategies = [
        MonthlyMAStrategy(
            broker,
            {"signal_asset": SYMBOL, "invest_amount": 10000},
            store=store,
            history_loader=lambda day: panel if day == signal_day else pl.DataFrame(),
        )
        for _, broker, store in paths
    ]
    try:
        remote.on_quote(
            datetime.datetime.combine(signal_day, datetime.time(15), tzinfo=get_timezone()),
            {SYMBOL: {"price": 9.99}},
        )
        paper.on_quote({SYMBOL: {"price": 9.99}})
        for strategy in strategies:
            await strategy.on_bar(
                datetime.datetime.combine(signal_day, datetime.time(15), tzinfo=get_timezone())
            )
        assert remote.query_trades() == []
        assert paper.query_trades() == []
        remote.on_quote(
            datetime.datetime.combine(execution_day, datetime.time(9, 30), tzinfo=get_timezone()),
            {SYMBOL: {"price": 9.99}},
        )
        paper.set_clock(
            datetime.datetime.combine(execution_day, datetime.time(9, 30), tzinfo=get_timezone())
        )
        paper.settle_t1()
        paper.on_quote({SYMBOL: {"price": 9.99}})
        for strategy in strategies:
            await strategy.on_bar(
                datetime.datetime.combine(
                    execution_day, datetime.time(9, 30), tzinfo=get_timezone()
                )
            )
        paper.on_quote({SYMBOL: {"price": 9.99}})
        assert [trade.shares for trade in remote.query_trades()] == [1000]
        assert [trade.price for trade in remote.query_trades()] == [9.99]
        assert remote.query_assets().cash == pytest.approx(10.0)
        assert paper.cash == pytest.approx(10.0)
        paper_positions = paper.positions
        assert sum(position.shares for position in paper_positions) == 1000
        assert backtest.cash == pytest.approx(10.0)
        backtest_positions = backtest.positions
        if isinstance(backtest_positions, dict):
            backtest_positions = backtest_positions.values()
        assert sum(position.shares for position in backtest_positions) == 1000
        for _, _, store in paths:
            assert store.pending() == []
    finally:
        paper.close()
        remote.close()
        db.close()


class RunnerDailyFeed:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame

    def get_price_for_match(self, asset, tm):
        return self.frame.filter((pl.col("asset") == asset) & (pl.col("date") == tm.date()))

    def get_trade_price_limits(self, asset, day):
        return 1.0, 10.0

    def get_bars(self, n, end=None, assets=None, **kwargs):
        frame = self.frame
        if end is not None:
            frame = frame.filter(pl.col("date") <= end)
        if assets:
            frame = frame.filter(pl.col("asset").is_in(assets))
        return frame.sort("date").tail(n)

    def get_bars_in_range(self, start, end=None, assets=None, **kwargs):
        frame = self.frame.filter(pl.col("date").is_between(start, end or start))
        if assets:
            frame = frame.filter(pl.col("asset").is_in(assets))
        return frame

    def get_close_adjust_factor(self, assets, start, end):
        return self.get_bars_in_range(start, end, assets).select("date", "asset", "close", "adjust")


@pytest.mark.asyncio
async def test_backtest_runner_monthly_signal_does_not_fill_before_next_open(tmp_path, monkeypatch):
    from quantide.data.models import daily_bars as daily_bars_module
    from quantide.service import runner as runner_module
    from quantide.strategies.example.monthly_ma import MonthlyMAStrategy

    calendar.load(Path(__file__).parents[2] / "assets" / "baseline_calendar.parquet")
    db.init(tmp_path / "runner-monthly.db")
    month_ends, execution_day = _monthly_days()
    first_day = month_ends[0]
    backtest_start = calendar.day_shift(first_day, 1)
    dates = list(calendar.get_trade_dates(first_day, execution_day))
    frame = pl.DataFrame(
        [
            {
                "date": day,
                "asset": SYMBOL,
                "open": 9.99
                if day == execution_day
                else (120.0 if day >= month_ends[-1] else 100.0),
                "close": 120.0 if day >= month_ends[-1] else 100.0,
                "high": 120.0 if day >= month_ends[-1] else 100.0,
                "low": 9.99 if day == execution_day else 100.0,
                "volume": 10000.0,
                "amount": 100000.0,
                "adjust": 1.0,
                "is_st": False,
                "up_limit": 10.0,
                "down_limit": 1.0,
            }
            for day in dates
        ]
    )
    feed = RunnerDailyFeed(frame)
    monkeypatch.setattr(runner_module, "daily_bars", feed)
    monkeypatch.setattr(daily_bars_module, "daily_bars", feed)
    observations: list[tuple[str, float]] = []

    class RecordingMonthly(MonthlyMAStrategy):
        async def on_bar(self, tm):
            await super().on_bar(tm)
            observations.append((tm.isoformat(), self.broker.cash))

    portfolio_id = "monthly-runner-clock"
    result = await runner_module.BacktestRunner().run(
        RecordingMonthly,
        {
            "signal_asset": SYMBOL,
            "invest_amount": 10000,
            "commission": 0.0,
            "min_commission": 0.0,
            "transfer_fee": 0.0,
            "stamp_duty": 0.0,
        },
        start_date=backtest_start,
        end_date=execution_day,
        frame_type=FrameType.MONTH,
        initial_cash=10000,
        portfolio_id=portfolio_id,
        db_path=str(tmp_path / "runner-monthly.db"),
    )
    assert result["metrics"]
    signal_tm = datetime.datetime.combine(
        month_ends[-1], datetime.time(15), tzinfo=get_timezone()
    ).isoformat()
    execution_tm = datetime.datetime.combine(
        execution_day, datetime.time(9, 30), tzinfo=get_timezone()
    ).isoformat()
    signal_cash = [cash for moment, cash in observations if moment == signal_tm]
    execution_cash = [cash for moment, cash in observations if moment == execution_tm]
    assert signal_cash == [10000.0]
    assert execution_cash == [10.0]
    trades = db.trades_all(portfolio_id).sort("tm")
    assert trades.height == 1
    assert trades["tm"].dt.date().to_list() == [execution_day]
    assert trades["price"].to_list() == [9.99]
    assert trades["shares"].to_list() == [1000.0]
    db.close()
