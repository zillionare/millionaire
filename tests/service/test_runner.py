import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

from quantide.core.enums import FrameType
from quantide.core.strategy import BaseStrategy
from quantide.data.sqlite import db
from quantide.service.runner import BacktestRunner


class SimpleStrategy(BaseStrategy):
    async def init(self):
        pass
    async def on_start(self):
        pass
    async def on_stop(self):
        pass
    async def on_day_open(self, tm):
        pass
    async def on_day_close(self, tm):
        pass
    async def on_bar(self, tm, quote, frame_type):
        pass


class _DailyQuoteFeed:
    def __init__(self):
        self._bars = pl.DataFrame(
            [
                {
                    "date": datetime.date(2024, 1, 4),
                    "asset": "000001.SZ",
                    "open": 10.0,
                    "close": 10.0,
                    "volume": 1000.0,
                    "up_limit": 11.0,
                    "down_limit": 9.0,
                },
                {
                    "date": datetime.date(2024, 1, 5),
                    "asset": "000001.SZ",
                    "open": 12.0,
                    "close": 12.0,
                    "volume": 1000.0,
                    "up_limit": 13.0,
                    "down_limit": 11.0,
                },
            ]
        )

    def get_bars_in_range(self, start, end, assets):
        start_date = start.date() if isinstance(start, datetime.datetime) else start
        end_date = end.date() if isinstance(end, datetime.datetime) else end
        return self._bars.filter(
            (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
            & pl.col("asset").is_in(assets)
        )


@pytest.fixture(autouse=True)
def setup_db():
    db.init(":memory:")
    yield
    # No explicit close method in SQLiteDB, but it's fine for memory db

@pytest.mark.asyncio
async def test_run_daily():
    start_date = datetime.date(2024, 1, 1)
    end_date = datetime.date(2024, 1, 2)

    # Mock dependencies
    with patch("quantide.service.runner.calendar") as mock_calendar, \
         patch("quantide.service.runner.BacktestBroker") as MockBroker, \
         patch("quantide.service.runner.daily_bars"), \
         patch("quantide.service.runner.db"), \
         patch("quantide.service.runner.metrics"):

        # Setup calendar mock
        mock_calendar.ceiling.return_value = start_date
        mock_calendar.floor.return_value = end_date
        mock_calendar.get_frames.return_value = [start_date, end_date]
        mock_calendar.replace_time.side_effect = lambda d, h, m: datetime.datetime(d.year, d.month, d.day, h, m)

        # Setup broker mock
        mock_broker_instance = MockBroker.return_value
        mock_broker_instance.stop_backtest = AsyncMock()
        mock_broker_instance.positions = {}

        # Setup strategy mock (spy)
        strategy = SimpleStrategy(mock_broker_instance, {})
        strategy.on_day_open = AsyncMock()
        strategy.on_day_close = AsyncMock()
        strategy.on_bar = AsyncMock()
        strategy.init = AsyncMock()
        strategy.on_start = AsyncMock()
        strategy.on_stop = AsyncMock()

        mock_clock = MagicMock()
        mock_clock.iter_frames.return_value = [start_date, end_date]

        # Run runner
        runner = BacktestRunner(clock=mock_clock)

        # Mock strategy_cls
        MockStrategyCls = MagicMock(return_value=strategy)
        MockStrategyCls.__name__ = "SimpleStrategy"
        MockStrategyCls.cheat_on_close = False  # 默认非 cheat 模式, 9:30 触发

        await runner.run(MockStrategyCls, {}, start_date, end_date, frame_type=FrameType.DAY)

        # Verify calls
        # 2 days -> 2 open, 2 bars, 2 closes
        assert strategy.on_day_open.call_count == 2
        assert strategy.on_bar.call_count == 2
        assert strategy.on_day_close.call_count == 2

        # Verify arguments
        # Day 1
        open_tm1 = datetime.datetime(2024, 1, 1, 9, 30)
        bar_tm1 = datetime.datetime(2024, 1, 1, 9, 30)
        close_tm1 = datetime.datetime(2024, 1, 1, 15, 30)

        strategy.on_day_open.assert_any_call(open_tm1)
        strategy.on_bar.assert_any_call(bar_tm1, {}, FrameType.DAY)
        strategy.on_day_close.assert_any_call(close_tm1)


def test_get_bar_quote_for_daily_backtest_uses_previous_completed_bar(monkeypatch):
    feed = _DailyQuoteFeed()
    monkeypatch.setattr("quantide.service.runner.daily_bars", feed)
    monkeypatch.setattr(
        "quantide.service.runner.calendar",
        MagicMock(day_shift=MagicMock(return_value=datetime.date(2024, 1, 4))),
    )

    runner = BacktestRunner()
    broker = MagicMock()
    broker.positions = {}

    quote = runner._get_bar_quote(
        broker,
        current_date=datetime.date(2024, 1, 5),
        bar_tm=datetime.datetime(2024, 1, 5, 9, 30),
        config={"universe": ["000001.SZ"]},
        frame_type=FrameType.DAY,
    )

    assert quote == {
        "000001.SZ": {
            "lastPrice": 10.0,
            "volume": 1000.0,
        }
    }

@pytest.mark.asyncio
async def test_run_minute():
    start_date = datetime.date(2024, 1, 1)
    end_date = datetime.date(2024, 1, 1) # 1 day

    # Mock dependencies
    with patch("quantide.service.runner.calendar") as mock_calendar, \
         patch("quantide.service.runner.BacktestBroker") as MockBroker, \
         patch("quantide.service.runner.daily_bars"), \
         patch("quantide.service.runner.db"), \
         patch("quantide.service.runner.metrics"):

        # Setup calendar mock
        mock_calendar.ceiling.return_value = start_date
        mock_calendar.floor.return_value = end_date
        # Minute frames: 9:31, 9:32 (just 2 frames for test)
        tm1 = datetime.datetime(2024, 1, 1, 9, 31)
        tm2 = datetime.datetime(2024, 1, 1, 9, 32)
        mock_calendar.get_frames.return_value = [tm1, tm2]

        mock_calendar.first_min_frame.return_value = datetime.datetime(2024, 1, 1, 9, 31)
        mock_calendar.last_min_frame.return_value = datetime.datetime(2024, 1, 1, 15, 0)

        mock_calendar.replace_time.side_effect = lambda d, h, m: datetime.datetime(d.year, d.month, d.day, h, m)

        # Setup broker mock
        mock_broker_instance = MockBroker.return_value
        mock_broker_instance.stop_backtest = AsyncMock()
        mock_broker_instance.positions = {}

        # Setup strategy mock
        strategy = SimpleStrategy(mock_broker_instance, {})
        strategy.on_day_open = AsyncMock()
        strategy.on_day_close = AsyncMock()
        strategy.on_bar = AsyncMock()
        strategy.init = AsyncMock()
        strategy.on_start = AsyncMock()
        strategy.on_stop = AsyncMock()

        MockStrategyCls = MagicMock(return_value=strategy)
        MockStrategyCls.__name__ = "SimpleStrategy"

        mock_clock = MagicMock()
        mock_clock.iter_frames.return_value = [tm1, tm2]

        runner = BacktestRunner(clock=mock_clock)
        await runner.run(MockStrategyCls, {}, start_date, end_date, frame_type=FrameType.MIN1)

        # Verify calls
        # 1 day -> 1 open, 2 bars, 1 close
        assert strategy.on_day_open.call_count == 1
        assert strategy.on_bar.call_count == 2
        assert strategy.on_day_close.call_count == 1

        # Verify arguments
        open_tm = datetime.datetime(2024, 1, 1, 9, 30)
        close_tm = datetime.datetime(2024, 1, 1, 15, 30)

        strategy.on_day_open.assert_called_once_with(open_tm)
        strategy.on_day_close.assert_called_once_with(close_tm)

        strategy.on_bar.assert_any_call(tm1, {}, FrameType.MIN1)
        strategy.on_bar.assert_any_call(tm2, {}, FrameType.MIN1)
