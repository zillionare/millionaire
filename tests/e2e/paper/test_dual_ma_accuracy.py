from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import BrokerKind, FrameType, OrderSide
from quantide.core.runtime.registration import register_port_backed_broker
from quantide.service.paper_broker_port import PaperBrokerPort
from quantide.data.models.calendar import calendar as calendar_model
from quantide.data.sqlite import db
from quantide.service.metrics import metrics
from quantide.service.registry import BrokerRegistry
from quantide.service.sim_broker import PaperBroker
from quantide.strategies.example.dual_ma import DualMAStrategy


ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
BASELINE_PATH = ASSETS_ROOT / "baselines" / "dual_ma_2024.backtest.json"
MARKET_PATH = ASSETS_ROOT / "2024_bars_ext_cols.parquet"
SYMBOL = "000001.SZ"


class ReplayMarketData:
    def __init__(self, bars: pl.DataFrame):
        self._bars = bars.sort("date")
        self._current_bar: dict[str, object] | None = None

    def set_bar(self, row: dict[str, object]) -> None:
        self._current_bar = row

    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        if self._current_bar is None:
            return {}
        symbol = str(self._current_bar["asset"])
        if symbol not in symbols:
            return {}
        open_price = float(self._current_bar["open"])
        return {
            symbol: QuoteSnapshot(
                symbol=symbol,
                price=open_price,
                open=open_price,
                high=float(self._current_bar["high"]),
                low=float(self._current_bar["low"]),
                volume=float(self._current_bar["volume"]),
                amount=float(self._current_bar["amount"]),
                ts=datetime.datetime.combine(
                    self._current_bar["date"],
                    datetime.time(9, 30),
                ),
            )
        }

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.date,
        frame_type: str = "1d",
    ) -> pl.DataFrame:
        _ = frame_type
        return (
            self._bars.filter(
                (pl.col("asset") == asset) & (pl.col("date") <= end_dt)
            )
            .sort("date")
            .tail(count)
        )


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text())


def _load_scenario_bars(baseline: dict) -> pl.DataFrame:
    start_date = datetime.date.fromisoformat(baseline["data"]["scenario_start"])
    end_date = datetime.date.fromisoformat(baseline["data"]["scenario_end"])
    return (
        pl.read_parquet(MARKET_PATH)
        .with_columns(pl.col("date").dt.date())
        .filter(
            (pl.col("asset") == SYMBOL)
            & (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
        )
        .sort("date")
    )


def _quote_payload(row: dict[str, object]) -> dict[str, float]:
    return {
        "lastPrice": float(row["open"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "volume": float(row["volume"]),
        "amount": float(row["amount"]),
    }


async def _replay_session_day(
    broker: PaperBroker,
    strategy: DualMAStrategy,
    market_data: ReplayMarketData,
    row: dict[str, object],
) -> None:
    session_open = datetime.datetime.combine(row["date"], datetime.time(9, 30))
    session_close = datetime.datetime.combine(row["date"], datetime.time(15, 0))
    market_data.set_bar(row)
    broker.set_clock(session_open)
    broker._on_limit_update(
        {
            SYMBOL: {
                "up": float(row["up_limit"]),
                "down": float(row["down_limit"]),
            }
        }
    )

    on_bar_task = asyncio.create_task(
        strategy.on_bar(
            session_open,
            {SYMBOL: _quote_payload(row)},
            FrameType.DAY,
        )
    )
    await asyncio.sleep(0.05)
    broker._on_quote_update({SYMBOL: _quote_payload(row)})
    await on_bar_task

    broker.set_clock(session_close)
    await broker.on_day_close(close_prices={SYMBOL: float(row["close"])})


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.release_gate
@pytest.mark.e2e_paper
@pytest.mark.xfail(
    reason="P3 待 PR3 重写: 当前调 PaperBroker._on_limit_update / _on_quote_update 私有方法 + patch.object(PaperBroker, '_get_today'), 违反 test-plan §5.4.6 边界铁律 (不得通过 mock.patch 内部符号 / 不得调私有方法). 重写需要 PaperBroker 暴露公开的 on_quote / on_limit 公开 API (PR2 范畴) + 配合 VirtualClock + make_paper_runtime. tracker: .dev/memory/26-06-22.md",
    strict=False,
)
async def test_dual_ma_paper_matches_accuracy_contract(calendar):
    _ = calendar
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT / "baseline_calendar.parquet")
    baseline = _load_baseline()
    bars = _load_scenario_bars(baseline)
    market_data = ReplayMarketData(bars)
    first_date = bars.row(0, named=True)["date"]
    portfolio_id = "dual-ma-paper-accuracy-contract"

    with patch.object(PaperBroker, "_get_today", return_value=first_date):
        legacy_broker = PaperBroker.create(
            portfolio_id=portfolio_id,
            principal=200000,
            commission=0.0005,
            market_data=market_data,
        )

    port = PaperBrokerPort(legacy_broker, portfolio_id=portfolio_id)
    handle = register_port_backed_broker(
        registry=BrokerRegistry(),
        port=port,
        portfolio_id=portfolio_id,
        kind=BrokerKind.SIMULATION,
    )
    strategy = DualMAStrategy(
        handle,
        {
            "symbol": SYMBOL,
            "fast": 5,
            "slow": 10,
            "invest": 100000,
            "universe": [SYMBOL],
        },
    )

    await strategy.init()
    await strategy.on_start()
    for row in bars.iter_rows(named=True):
        await _replay_session_day(legacy_broker, strategy, market_data, row)
    await strategy.on_stop()

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

    actual_assets = [
        {
            "dt": str(row["dt"]),
            "cash": round(float(row["cash"]), 6),
            "market_value": round(float(row["market_value"]), 6),
            "total": round(float(row["total"]), 6),
        }
        for row in assets.iter_rows(named=True)
        if str(row["dt"]) >= baseline["equity_curve"][0]["dt"]
    ]
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

    stats = metrics(
        portfolio_id,
        start=datetime.date.fromisoformat(baseline["data"]["scenario_start"]),
        end=datetime.date.fromisoformat(baseline["metrics"]["raw"]["end_date"]),
    )
    assert stats is not None
    assert stats.loc["Start Date", "Value"] == baseline["metrics"]["raw"]["start_date"]
    assert stats.loc["End Date", "Value"] == baseline["metrics"]["raw"]["end_date"]
    assert int(stats.loc["Total Trading Days", "Value"]) == baseline["metrics"]["raw"]["trading_days"]
    assert stats.loc["Total Return", "Value"] == baseline["metrics"]["formatted"]["Total Return"]
    assert stats.loc["CAGR", "Value"] == baseline["metrics"]["formatted"]["CAGR"]
    assert stats.loc["Volatility (ann.)", "Value"] == baseline["metrics"]["formatted"]["Volatility (ann.)"]
    assert stats.loc["Sharpe Ratio", "Value"] == baseline["metrics"]["formatted"]["Sharpe Ratio"]
    assert stats.loc["Max Drawdown", "Value"] == baseline["metrics"]["formatted"]["Max Drawdown"]