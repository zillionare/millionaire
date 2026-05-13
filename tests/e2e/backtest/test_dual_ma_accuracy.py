from __future__ import annotations

import datetime
import json
from pathlib import Path

import polars as pl
import pytest

from quantide.core.enums import FrameType, OrderSide
from quantide.data.models.calendar import calendar as calendar_model
from quantide.data.sqlite import db
from quantide.service import runner as runner_module
from quantide.service.runner import BacktestRunner
from quantide.strategies.example.dual_ma import DualMAStrategy


ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
BASELINE_PATH = ASSETS_ROOT / "baselines" / "dual_ma_2024.backtest.json"


class FixtureFeed:
    def __init__(self, frame: pl.DataFrame):
        self._bars = frame.sort("date")

    def _filter(self, start=None, end=None, assets=None) -> pl.DataFrame:
        df = self._bars
        if assets:
            df = df.filter(pl.col("asset").is_in(assets))
        if start is not None:
            start_date = start.date() if isinstance(start, datetime.datetime) else start
            df = df.filter(pl.col("date") >= start_date)
        if end is not None:
            end_date = end.date() if isinstance(end, datetime.datetime) else end
            df = df.filter(pl.col("date") <= end_date)
        return df.sort("date")

    def get_bars_in_range(self, start, end=None, assets=None, adjust="qfq", eager_mode=True):
        _ = adjust
        _ = eager_mode
        return self._filter(start=start, end=end, assets=assets)

    def get_bars(self, n, end=None, assets=None, adjust="qfq", eager_mode=True):
        _ = adjust
        _ = eager_mode
        return self._filter(end=end, assets=assets).tail(n)

    def get_price_for_match(self, asset, tm):
        return self._filter(start=tm.date(), end=tm.date(), assets=[asset])

    def get_trade_price_limits(self, asset, dt_value):
        df = self._filter(start=dt_value, end=dt_value, assets=[asset])
        row = df.row(0, named=True)
        return float(row["down_limit"]), float(row["up_limit"])

    def get_close_adjust_factor(self, assets, start, end):
        return self._filter(start=start, end=end, assets=assets).select(
            pl.col("date"),
            pl.col("asset"),
            pl.col("close"),
            pl.col("adjust"),
        )


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text())


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.release_gate
async def test_dual_ma_backtest_matches_accuracy_contract(calendar):
    _ = calendar
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT / "baseline_calendar.parquet")
    baseline = _load_baseline()
    feed = FixtureFeed(
        pl.read_parquet(ASSETS_ROOT / "2024_bars_ext_cols.parquet").with_columns(
            pl.col("date").dt.date()
        )
    )
    runner_module.daily_bars = feed

    portfolio_id = "dual-ma-accuracy-contract"
    result = await BacktestRunner().run(
        DualMAStrategy,
        {
            "symbol": "000001.SZ",
            "fast": 5,
            "slow": 10,
            "invest": 100000,
            "universe": ["000001.SZ"],
        },
        start_date=datetime.date(2024, 1, 2),
        end_date=datetime.date(2024, 5, 31),
        frame_type=FrameType.DAY,
        initial_cash=200000,
        portfolio_id=portfolio_id,
    )

    trades = db.trades_all(portfolio_id=portfolio_id).sort("tm")
    orders = db.orders_all(portfolio_id=portfolio_id).sort("tm")
    assets = db.assets_all(portfolio_id=portfolio_id).sort("dt")

    assert trades.height == len(baseline["trades"]) == 14
    assert orders.height == trades.height
    assert orders["qtoid"].n_unique() == orders.height
    assert trades["qtoid"].to_list() == orders["qtoid"].to_list()

    for actual, expected in zip(trades.iter_rows(named=True), baseline["trades"], strict=True):
        trade_date = actual["tm"].date()
        assert str(trade_date) == expected["trade_date"]
        assert calendar_model.day_shift(trade_date, -1).isoformat() == expected["signal_date"]
        assert OrderSide(actual["side"]).name == expected["side"]
        assert int(actual["shares"]) == expected["shares"]
        assert round(float(actual["price"]), 6) == expected["price"]
        assert round(float(actual["amount"]), 6) == expected["amount"]
        assert round(float(actual["fee"]), 6) == expected["fee"]

    actual_assets = []
    for row in assets.iter_rows(named=True):
        if str(row["dt"]) < baseline["equity_curve"][0]["dt"]:
            continue
        actual_assets.append(
            {
                "dt": str(row["dt"]),
                "cash": round(float(row["cash"]), 6),
                "market_value": round(float(row["market_value"]), 6),
                "total": round(float(row["total"]), 6),
            }
        )

    expected_assets = [
        {
            "dt": row["dt"],
            "cash": row["cash"],
            "market_value": row["market_value"],
            "total": row["total"],
        }
        for row in baseline["equity_curve"]
    ]
    assert actual_assets == expected_assets

    stats = result["metrics"]["Value"]
    assert stats["Start Date"] == baseline["metrics"]["raw"]["start_date"]
    assert stats["End Date"] == baseline["metrics"]["raw"]["end_date"]
    assert stats["Total Trading Days"] == baseline["metrics"]["raw"]["trading_days"]
    assert stats["Total Return"] == baseline["metrics"]["formatted"]["Total Return"]
    assert stats["CAGR"] == baseline["metrics"]["formatted"]["CAGR"]
    assert stats["Volatility (ann.)"] == baseline["metrics"]["formatted"]["Volatility (ann.)"]
    assert stats["Sharpe Ratio"] == baseline["metrics"]["formatted"]["Sharpe Ratio"]
    assert stats["Max Drawdown"] == baseline["metrics"]["formatted"]["Max Drawdown"]