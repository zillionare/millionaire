"""#20 forming realtime daily bars — test forming-bar synthesis at broker.get_history.

Issue #20: 策略在 live/paper 模式调用 get_history() 拿到含今日 forming bar
的 DataFrame，close 必须反映 latest tick price，不是昨日 close。
"""

from __future__ import annotations

import datetime
import json
import threading
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from quantide.core.message import msg_hub
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.calendar import calendar
from quantide.data.sqlite import db
from quantide.service.livequote import LiveQuote, live_quote
from quantide.service.sim_broker import PaperBroker, SimulationBroker
from quantide.core.runtime.gateway_broker import GatewayBrokerWrapper
from quantide.core.enums import BrokerKind


# --- Test data setup ---

ASSETS_ROOT = Path(__file__).resolve().parent.parent / "assets"
TEST_BARS_PARQUET = ASSETS_ROOT / "2024_bars.parquet"
TEST_CALENDAR_PARQUET = ASSETS_ROOT / "baseline_calendar.parquet"
TEST_ASSET = "688371.SH"  # 出现在测试 parquet 中


def _reset_singletons() -> None:
    """每个测试前重置单例，避开测试间状态污染。"""
    LiveQuote._instance = None
    daily_bars._instance = None
    calendar._instance = None
    daily_bars._initialized = False
    calendar._initialized = False


def _ingest_tick(
    asset: str,
    *,
    timestamp: float,
    m1: dict[str, Any] | None = None,
    d1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """模拟一次 gateway 推送（直接调 _parse_ws_payload 喂给 LiveQuote）.

    Returns:
        parsed payload dict
    """
    raw = json.dumps(
        {
            "symbol": asset,
            "timestamp": timestamp,
            "1m": m1 or {},
            "1d": d1 or {},
        }
    )
    return live_quote._parse_ws_payload(raw)


def _seed_daily_bars(days: int = 5, asset: str = TEST_ASSET) -> list[datetime.date]:
    """把 daily_bars._store 指向测试 parquet 的子集（只取该 asset 最近 days 天）.

    Returns:
        按时间正序的交易日列表。
    """
    df = pl.read_parquet(TEST_BARS_PARQUET)
    sub = df.filter(pl.col("asset") == asset).sort("date")
    sub = sub.tail(days)
    from quantide.data.stores.bars import DailyBarsStore
    from quantide.data.models.calendar import Calendar
    cal = Calendar().load(TEST_CALENDAR_PARQUET)
    sub_all = df.filter(pl.col("asset") == asset).sort("date")
    store = DailyBarsStore.__new__(DailyBarsStore)
    store._frame = sub_all
    store._calendar = cal
    daily_bars._store = store
    daily_bars._calendar = cal
    return [d.date() if hasattr(d, "date") else d for d in sub_all.get_column("date").to_list()]


# --- 核心契约测试 ---


def test_livequote_aggregates_forming_daily_bar_ohlc():
    """从第一个 tick 起 OHLC 实时累积，今日 forming bar 字段可读。"""
    _reset_singletons()
    # 推送 3 个 tick：open=10, high=10.5, low=9.8, close 在 tick 间变化
    base = datetime.datetime(2024, 6, 3, 9, 30, 0).timestamp()
    _ingest_tick(
        TEST_ASSET,
        timestamp=base,
        m1={"open": 10.0, "high": 10.3, "low": 9.9, "close": 10.1, "vol": 100, "amount": 1010},
        d1={"open": 9.8, "high": 10.5, "low": 9.7, "close": 10.1, "vol": 200, "amount": 2000},
    )
    _ingest_tick(
        TEST_ASSET,
        timestamp=base + 60,
        m1={"open": 10.0, "high": 10.4, "low": 9.95, "close": 10.25, "vol": 200, "amount": 2050},
        d1={"open": 9.8, "high": 10.6, "low": 9.7, "close": 10.25, "vol": 400, "amount": 4100},
    )
    _ingest_tick(
        TEST_ASSET,
        timestamp=base + 120,
        m1={"open": 10.0, "high": 10.45, "low": 9.95, "close": 10.20, "vol": 150, "amount": 1530},
        d1={"open": 9.8, "high": 10.6, "low": 9.75, "close": 10.20, "vol": 500, "amount": 5100},
    )
    bar = live_quote.get_daily_bar(TEST_ASSET)
    assert bar is not None
    # forming bar 字段：open/high/low 来自 1d 累积；close 用最新价；volume 累积
    assert bar["open"] == pytest.approx(9.8)  # 1d 第一个 tick 的 open
    assert bar["high"] == pytest.approx(10.6)  # 三个 tick 中最高
    assert bar["low"] == pytest.approx(9.75)  # 三个 tick 中最低
    assert bar["close"] == pytest.approx(10.20)  # 最新 tick 的 1d.close
    assert bar["volume"] == pytest.approx(1100)  # 累计
    assert bar["frame"] == "1d"
    # dt 应该是今天
    assert bar["dt"] == datetime.date(2024, 6, 3)


def test_sim_broker_get_history_includes_forming_bar_by_default():
    """Paper 模式 get_history 默认应包含今日 forming bar，close=最新 tick 价。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]
    yesterday = trade_dates[-2]
    yesterday_close_expected = None

    df = pl.read_parquet(TEST_BARS_PARQUET).filter(pl.col("asset") == TEST_ASSET)
    yesterday_row = df.filter(pl.col("date").dt.date() == yesterday).row(0, named=True)
    yesterday_close_expected = float(yesterday_row["close"])

    base = datetime.datetime.combine(today, datetime.time(14, 55)).timestamp()
    _ingest_tick(
        TEST_ASSET,
        timestamp=base,
        m1={"open": 11.0, "high": 11.3, "low": 10.9, "close": 11.20, "vol": 500, "amount": 5600},
        d1={"open": 10.5, "high": 11.5, "low": 10.4, "close": 11.20, "vol": 1000, "amount": 11000},
    )
    _ingest_tick(
        TEST_ASSET,
        timestamp=base + 60,
        m1={"open": 11.0, "high": 11.35, "low": 10.95, "close": 11.28, "vol": 600, "amount": 6770},
        d1={"open": 10.5, "high": 11.5, "low": 10.45, "close": 11.28, "vol": 1500, "amount": 16800},
    )

    broker = PaperBroker(
        portfolio_id="sim_forming",
        principal=1_000_000,
    )
    try:
        df_hist = broker.get_history(
            TEST_ASSET, count=5, end_dt=datetime.datetime.combine(today, datetime.time(15, 0))
        )
    finally:
        broker._teardown_subscriptions()
    # forming bar 必须在最后一行
    assert len(df_hist) == 5
    last_row = df_hist.row(-1, named=True)
    last_close = float(last_row["close"])
    last_date = last_row["date"]
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    # forming bar 必须是今日
    assert last_date == today, f"expected forming bar at {today}, got {last_date}"
    # close 必须是最新 tick (11.28)，不是昨日 close
    assert last_close == pytest.approx(11.28, rel=0.01), (
        f"forming bar close should be 11.28, got {last_close} (yesterday was {yesterday_close_expected})"
    )
    assert last_close != yesterday_close_expected


def test_sim_broker_get_history_excludes_forming_bar_when_disabled():
    """include_forming_bar=False → 最后一行是昨日历史，不含今日。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]
    yesterday = trade_dates[-2]

    base = datetime.datetime.combine(today, datetime.time(14, 55)).timestamp()
    _ingest_tick(
        TEST_ASSET,
        timestamp=base,
        m1={"close": 99.99, "vol": 1, "amount": 99.99},
        d1={"open": 10, "high": 12, "low": 9, "close": 99.99, "vol": 1, "amount": 99.99},
    )

    broker = PaperBroker(portfolio_id="sim_no_forming", principal=1_000_000)
    try:
        df_hist = broker.get_history(
            TEST_ASSET,
            count=5,
            end_dt=datetime.datetime.combine(today, datetime.time(15, 0)),
            include_forming_bar=False,
        )
    finally:
        broker._teardown_subscriptions()
    last_row = df_hist.row(-1, named=True)
    last_date = last_row["date"]
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    assert last_date == yesterday
    # 关键是 close 应该是昨日 close，不是 99.99
    assert float(last_row["close"]) != pytest.approx(99.99)


def test_sim_broker_get_history_past_end_date_excludes_forming():
    """end_dt=昨日 → 无论如何都不含今日 forming。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]
    yesterday = trade_dates[-2]

    base = datetime.datetime.combine(today, datetime.time(14, 55)).timestamp()
    _ingest_tick(
        TEST_ASSET,
        timestamp=base,
        m1={"close": 99.99},
        d1={"open": 10, "high": 12, "low": 9, "close": 99.99, "vol": 1, "amount": 99.99},
    )

    broker = PaperBroker(portfolio_id="sim_past_end", principal=1_000_000)
    try:
        df_hist = broker.get_history(
            TEST_ASSET,
            count=3,
            end_dt=datetime.datetime.combine(yesterday, datetime.time(15, 0)),
            include_forming_bar=True,
        )
    finally:
        broker._teardown_subscriptions()
    last_row = df_hist.row(-1, named=True)
    last_date = last_row["date"]
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    assert last_date == yesterday


def test_gateway_broker_get_history_includes_forming_bar():
    """Live 模式 get_history 默认含 forming bar。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]
    yesterday = trade_dates[-2]

    df = pl.read_parquet(TEST_BARS_PARQUET).filter(pl.col("asset") == TEST_ASSET)
    yesterday_close = float(
        df.filter(pl.col("date").dt.date() == yesterday).row(0, named=True)["close"]
    )

    base = datetime.datetime.combine(today, datetime.time(14, 55)).timestamp()
    _ingest_tick(
        TEST_ASSET,
        timestamp=base,
        m1={"close": 12.34, "vol": 100, "amount": 1234},
        d1={"open": 10, "high": 13, "low": 9, "close": 12.34, "vol": 500, "amount": 6000},
    )

    broker = GatewayBrokerWrapper(
        portfolio_id="gw_forming",
        kind=BrokerKind.QMT,
        history_provider=daily_bars,
    )
    df_hist = broker.get_history(
        TEST_ASSET,
        count=5,
        end_dt=datetime.datetime.combine(today, datetime.time(15, 0)),
    )
    last_row = df_hist.row(-1, named=True)
    last_date = last_row["date"]
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    assert last_date == today
    assert float(last_row["close"]) == pytest.approx(12.34, rel=0.01)
    assert float(last_row["close"]) != yesterday_close


def test_gateway_broker_get_history_disabled_excludes_forming():
    """Live 模式 include_forming_bar=False → 历史不漂移到今日。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]
    yesterday = trade_dates[-2]

    base = datetime.datetime.combine(today, datetime.time(14, 55)).timestamp()
    _ingest_tick(
        TEST_ASSET,
        timestamp=base,
        m1={"close": 99.99},
        d1={"close": 99.99},
    )

    broker = GatewayBrokerWrapper(
        portfolio_id="gw_no_forming",
        kind=BrokerKind.QMT,
        history_provider=daily_bars,
    )
    df_hist = broker.get_history(
        TEST_ASSET,
        count=5,
        end_dt=datetime.datetime.combine(today, datetime.time(15, 0)),
        include_forming_bar=False,
    )
    last_row = df_hist.row(-1, named=True)
    last_date = last_row["date"]
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    assert last_date == yesterday


def test_no_forming_bar_when_livequote_silent():
    """如果 LiveQuote 还没收到任何 tick，get_history 不应假造 forming bar。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]
    yesterday = trade_dates[-2]

    # 注意：没有 _ingest_tick
    broker = PaperBroker(portfolio_id="sim_silent", principal=1_000_000)
    try:
        df_hist = broker.get_history(
            TEST_ASSET,
            count=5,
            end_dt=datetime.datetime.combine(today, datetime.time(15, 0)),
        )
    finally:
        broker._teardown_subscriptions()
    last_row = df_hist.row(-1, named=True)
    last_date = last_row["date"]
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    assert last_date == yesterday  # 没有 forming bar 注入


def test_strategy_get_history_passes_through_include_forming():
    """strategy.get_history 必须把 include_forming_bar 传给 broker.get_history."""
    _reset_singletons()
    captured_kwargs: dict[str, Any] = {}

    class _RecordingBroker:
        def get_history(self, asset, count, end_dt=None, frame_type="1d", **kwargs):
            captured_kwargs.update(kwargs)
            return pl.DataFrame()

        @property
        def portfolio_id(self) -> str:
            return "rec"

        @property
        def kind(self) -> BrokerKind:
            return BrokerKind.SIMULATION

    from quantide.core.strategy import BaseStrategy

    strategy = BaseStrategy.__new__(BaseStrategy)
    strategy.broker = _RecordingBroker()
    strategy.logger = None
    strategy.interval = "1d"
    strategy._current_time = None

    strategy.get_history(TEST_ASSET, 5, include_forming_bar=False)
    assert captured_kwargs.get("include_forming_bar") is False

    strategy.get_history(TEST_ASSET, 5, include_forming_bar=True)
    assert captured_kwargs.get("include_forming_bar") is True

    # 默认应视为 True
    strategy.get_history(TEST_ASSET, 5)
    assert captured_kwargs.get("include_forming_bar") is True


def test_forming_bar_at_1455_uses_latest_tick_close():
    """14:55 场景：今日 forming bar 的 close 应是 14:55 那一刻的最新 tick 价。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]

    # 模拟盘中 9:31, 11:00, 14:00, 14:55 四个 tick
    tick_times = [
        (datetime.time(9, 31), 10.10),
        (datetime.time(11, 0), 10.25),
        (datetime.time(14, 0), 10.40),
        (datetime.time(14, 55), 10.55),
    ]
    for tm, price in tick_times:
        ts = datetime.datetime.combine(today, tm).timestamp()
        _ingest_tick(
            TEST_ASSET,
            timestamp=ts,
            m1={"close": price, "vol": 100, "amount": price * 100},
            d1={
                "open": 10.0,
                "high": price + 0.1,
                "low": price - 0.1,
                "close": price,
                "vol": 1000,
                "amount": price * 1000,
            },
        )

    broker = PaperBroker(portfolio_id="sim_1455", principal=1_000_000)
    try:
        df_hist = broker.get_history(
            TEST_ASSET,
            count=5,
            end_dt=datetime.datetime.combine(today, datetime.time(14, 55)),
        )
    finally:
        broker._teardown_subscriptions()
    last_row = df_hist.row(-1, named=True)
    # 14:55 那一刻的 close 应该是 10.55，不是昨日 close
    assert float(last_row["close"]) == pytest.approx(10.55, rel=0.001)


def test_forming_bar_open_uses_today_open_not_yesterday_close():
    """今日 forming bar 的 open 应来自 1d.open（gateway 给的今日开盘价），
    不是昨日 close。这避免了 forming bar 跨交易日时 open 跳变到昨日 close 的常见错误。"""
    _reset_singletons()
    trade_dates = _seed_daily_bars(days=5)
    today = trade_dates[-1]
    yesterday = trade_dates[-2]

    df = pl.read_parquet(TEST_BARS_PARQUET).filter(pl.col("asset") == TEST_ASSET)
    yesterday_close = float(
        df.filter(pl.col("date").dt.date() == yesterday).row(0, named=True)["close"]
    )

    base = datetime.datetime.combine(today, datetime.time(9, 31)).timestamp()
    _ingest_tick(
        TEST_ASSET,
        timestamp=base,
        m1={"open": 20.0, "high": 20.5, "low": 19.5, "close": 20.0, "vol": 100, "amount": 2000},
        d1={"open": 20.0, "high": 20.5, "low": 19.5, "close": 20.0, "vol": 100, "amount": 2000},
    )

    broker = PaperBroker(portfolio_id="sim_open", principal=1_000_000)
    try:
        df_hist = broker.get_history(
            TEST_ASSET,
            count=5,
            end_dt=datetime.datetime.combine(today, datetime.time(15, 0)),
        )
    finally:
        broker._teardown_subscriptions()
    last_row = df_hist.row(-1, named=True)
    # open 应该是今日 1d.open = 20.0，不是 yesterday_close
    assert float(last_row["open"]) == pytest.approx(20.0)
    assert float(last_row["open"]) != yesterday_close
