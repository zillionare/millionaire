from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import polars as pl
import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import BrokerKind, FrameType, OrderSide
from quantide.core.runtime.adapter_registry import AdapterRegistry
from quantide.core.runtime.gateway_broker import GatewayBrokerAdapter, GatewayBrokerWrapper
from quantide.core.runtime.gateway_client import GatewayClient
from quantide.core.runtime.registration import register_legacy_broker, register_port_backed_broker
from quantide.data.models.calendar import calendar as calendar_model
from quantide.data.sqlite import Asset, db
from quantide.service import runner as runner_module
from quantide.service.metrics import metrics
from quantide.service.registry import BrokerRegistry
from quantide.service.runner import BacktestRunner
from quantide.service.sim_broker import PaperBroker
from quantide.service.strategy_runtime import StrategyBrokerProxy
from quantide.strategies.example.dual_ma import DualMAStrategy
from tests.e2e.support.gateway_stub import GatewayScenario, GatewaySubmitScript, running_gateway_stub


ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
BASELINE_PATH = ASSETS_ROOT / "baselines" / "dual_ma_2024.backtest.json"
MARKET_PATH = ASSETS_ROOT / "2024_bars_ext_cols.parquet"
SYMBOL = "000001.SZ"
INITIAL_CASH = 200000.0


class ScenarioFeed:
    def __init__(self, frame: pl.DataFrame):
        self._bars = frame.sort("date")
        self._current_bar: dict[str, object] | None = None

    def set_bar(self, row: dict[str, object]) -> None:
        self._current_bar = row

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

    def get_price_limits(self, asset: str) -> tuple[float, float]:
        if self._current_bar is None or str(self._current_bar["asset"]) != asset:
            return 0.0, 0.0
        return (
            float(self._current_bar["down_limit"]),
            float(self._current_bar["up_limit"]),
        )


def _load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE_PATH.read_text())


def _load_scenario_bars(baseline: dict[str, Any]) -> pl.DataFrame:
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


def _strategy_config() -> dict[str, Any]:
    return {
        "symbol": SYMBOL,
        "fast": 5,
        "slow": 10,
        "invest": 100000,
        "universe": [SYMBOL],
    }


def _quote_payload(row: dict[str, object]) -> dict[str, float]:
    return {
        "lastPrice": float(row["open"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "volume": float(row["volume"]),
        "amount": float(row["amount"]),
    }


def _expected_trade_facts(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "signal_date": row["signal_date"],
            "trade_date": row["trade_date"],
            "side": row["side"],
            "shares": row["shares"],
            "price": row["price"],
            "amount": row["amount"],
        }
        for row in baseline["trades"]
    ]


def _expected_equity_curve(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "dt": row["dt"],
            "cash": row["cash"],
            "market_value": row["market_value"],
            "total": row["total"],
        }
        for row in baseline["equity_curve"]
    ]


def _expected_metrics(baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "Start Date": baseline["metrics"]["raw"]["start_date"],
        "End Date": baseline["metrics"]["raw"]["end_date"],
        "Total Trading Days": baseline["metrics"]["raw"]["trading_days"],
        "Total Return": baseline["metrics"]["formatted"]["Total Return"],
        "CAGR": baseline["metrics"]["formatted"]["CAGR"],
        "Volatility (ann.)": baseline["metrics"]["formatted"]["Volatility (ann.)"],
        "Sharpe Ratio": baseline["metrics"]["formatted"]["Sharpe Ratio"],
        "Max Drawdown": baseline["metrics"]["formatted"]["Max Drawdown"],
    }


def _metrics_snapshot(stats) -> dict[str, Any]:
    return {
        "Start Date": stats.loc["Start Date", "Value"],
        "End Date": stats.loc["End Date", "Value"],
        "Total Trading Days": int(stats.loc["Total Trading Days", "Value"]),
        "Total Return": stats.loc["Total Return", "Value"],
        "CAGR": stats.loc["CAGR", "Value"],
        "Volatility (ann.)": stats.loc["Volatility (ann.)", "Value"],
        "Sharpe Ratio": stats.loc["Sharpe Ratio", "Value"],
        "Max Drawdown": stats.loc["Max Drawdown", "Value"],
    }


def _db_trade_facts(portfolio_id: str) -> list[dict[str, Any]]:
    trades = db.trades_all(portfolio_id=portfolio_id).sort("tm")
    facts: list[dict[str, Any]] = []
    for actual in trades.iter_rows(named=True):
        trade_date = actual["tm"].date()
        facts.append(
            {
                "signal_date": calendar_model.day_shift(trade_date, -1).isoformat(),
                "trade_date": trade_date.isoformat(),
                "side": OrderSide(actual["side"]).name,
                "shares": int(actual["shares"]),
                "price": round(float(actual["price"]), 6),
                "amount": round(float(actual["amount"]), 6),
            }
        )
    return facts


def _live_trade_facts(trades: list[Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for trade in sorted(trades, key=lambda item: item.tm):
        trade_date = trade.tm.date()
        facts.append(
            {
                "signal_date": calendar_model.day_shift(trade_date, -1).isoformat(),
                "trade_date": trade_date.isoformat(),
                "side": str(trade.side).upper(),
                "shares": int(trade.shares),
                "price": round(float(trade.price), 6),
                "amount": round(float(trade.amount), 6),
            }
        )
    return facts


def _db_equity_curve(portfolio_id: str, start_dt: str) -> list[dict[str, Any]]:
    assets = db.assets_all(portfolio_id=portfolio_id).sort("dt")
    return [
        {
            "dt": str(row["dt"]),
            "cash": round(float(row["cash"]), 6),
            "market_value": round(float(row["market_value"]), 6),
            "total": round(float(row["total"]), 6),
        }
        for row in assets.iter_rows(named=True)
        if str(row["dt"]) >= start_dt
    ]


def _build_live_submit_scripts(baseline: dict[str, Any]) -> list[GatewaySubmitScript]:
    scripts: list[GatewaySubmitScript] = []
    for index, row in enumerate(baseline["trades"], start=1):
        position_after = int(row["position_after"])
        market_value_after = float(row["market_value_after"])
        positions_after = []
        if position_after > 0:
            positions_after = [
                {
                    "symbol": SYMBOL,
                    "shares": position_after,
                    "avail": position_after,
                    "cost": round((float(row["amount"]) + float(row["fee"])) / position_after, 6),
                    "market_value": market_value_after,
                }
            ]
        scripts.append(
            GatewaySubmitScript(
                side=str(row["side"]).lower(),
                symbol=SYMBOL,
                response={"success": True, "order_id": f"ext-parity-{index}"},
                order={
                    "symbol": SYMBOL,
                    "side": str(row["side"]).lower(),
                    "shares": int(row["shares"]),
                    "price": float(row["price"]),
                    "status": "filled",
                    "filled": int(row["shares"]),
                    "time": f"{row['trade_date']} 09:30:00",
                },
                trades=[
                    {
                        "tid": f"gw-parity-{index}",
                        "symbol": SYMBOL,
                        "side": str(row["side"]).lower(),
                        "shares": int(row["shares"]),
                        "price": float(row["price"]),
                        "amount": float(row["amount"]),
                        "fee": float(row["fee"]),
                        "time": f"{row['trade_date']} 09:30:05",
                    }
                ],
                asset_after={
                    "principal": INITIAL_CASH,
                    "cash": float(row["cash_after"]),
                    "market_value": market_value_after,
                    "total": float(row["total_after"]),
                    "frozen_cash": 0.0,
                },
                positions_after=positions_after,
                expose_order_qtoid=False,
                expose_trade_qtoid=False,
            )
        )
    return scripts


async def _replay_paper_session_day(
    broker: PaperBroker,
    strategy: DualMAStrategy,
    market_data: ScenarioFeed,
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


async def _run_backtest_mode(baseline: dict[str, Any], feed: ScenarioFeed) -> dict[str, Any]:
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT / "baseline_calendar.parquet")
    original_daily_bars = runner_module.daily_bars
    runner_module.daily_bars = feed
    try:
        result = await BacktestRunner().run(
            DualMAStrategy,
            _strategy_config(),
            start_date=datetime.date.fromisoformat(baseline["data"]["scenario_start"]),
            end_date=datetime.date.fromisoformat(baseline["data"]["scenario_end"]),
            frame_type=FrameType.DAY,
            initial_cash=INITIAL_CASH,
            portfolio_id="dual-ma-parity-backtest",
        )
        return {
            "trades": _db_trade_facts("dual-ma-parity-backtest"),
            "equity_curve": _db_equity_curve(
                "dual-ma-parity-backtest",
                baseline["equity_curve"][0]["dt"],
            ),
            "metrics": {
                "Start Date": result["metrics"]["Value"]["Start Date"],
                "End Date": result["metrics"]["Value"]["End Date"],
                "Total Trading Days": result["metrics"]["Value"]["Total Trading Days"],
                "Total Return": result["metrics"]["Value"]["Total Return"],
                "CAGR": result["metrics"]["Value"]["CAGR"],
                "Volatility (ann.)": result["metrics"]["Value"]["Volatility (ann.)"],
                "Sharpe Ratio": result["metrics"]["Value"]["Sharpe Ratio"],
                "Max Drawdown": result["metrics"]["Value"]["Max Drawdown"],
            },
        }
    finally:
        runner_module.daily_bars = original_daily_bars


async def _run_paper_mode(baseline: dict[str, Any], bars: pl.DataFrame) -> dict[str, Any]:
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT / "baseline_calendar.parquet")
    market_data = ScenarioFeed(bars)
    first_date = bars.row(0, named=True)["date"]
    portfolio_id = "dual-ma-parity-paper"

    with patch.object(PaperBroker, "_get_today", return_value=first_date):
        legacy_broker = PaperBroker.create(
            portfolio_id=portfolio_id,
            principal=INITIAL_CASH,
            commission=0.0005,
            market_data=market_data,
        )

    handle = register_legacy_broker(
        registry=BrokerRegistry(),
        broker=legacy_broker,
        portfolio_id=portfolio_id,
        kind=BrokerKind.SIMULATION,
    )
    strategy = DualMAStrategy(handle, _strategy_config())
    await strategy.init()
    await strategy.on_start()
    for row in bars.iter_rows(named=True):
        await _replay_paper_session_day(legacy_broker, strategy, market_data, row)
    await strategy.on_stop()

    stats = metrics(
        portfolio_id,
        start=datetime.date.fromisoformat(baseline["data"]["scenario_start"]),
        end=datetime.date.fromisoformat(baseline["metrics"]["raw"]["end_date"]),
    )
    assert stats is not None
    return {
        "trades": _db_trade_facts(portfolio_id),
        "equity_curve": _db_equity_curve(portfolio_id, baseline["equity_curve"][0]["dt"]),
        "metrics": _metrics_snapshot(stats),
    }


async def _run_live_mode(baseline: dict[str, Any], bars: pl.DataFrame) -> dict[str, Any]:
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT / "baseline_calendar.parquet")
    market_data = ScenarioFeed(bars)
    portfolio_id = "dual-ma-parity-live"
    live_curve: list[dict[str, Any]] = []

    scenario = GatewayScenario(
        asset={
            "principal": INITIAL_CASH,
            "total": INITIAL_CASH,
            "cash": INITIAL_CASH,
            "market_value": 0.0,
            "frozen_cash": 0.0,
        },
        submit_scripts=_build_live_submit_scripts(baseline),
    )

    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        client = GatewayClient(stub.base_url, username="u", password="p", timeout=2)
        adapter = GatewayBrokerAdapter(client, market_data=market_data)
        wrapper = GatewayBrokerWrapper(adapter, history_provider=market_data)
        handle = register_port_backed_broker(
            registry=BrokerRegistry(),
            adapters=AdapterRegistry(),
            port=adapter,
            portfolio_id="gateway",
            kind=BrokerKind.QMT,
            legacy=wrapper,
        )
        broker = StrategyBrokerProxy(handle, "dual-ma-parity-live")
        strategy = DualMAStrategy(broker, _strategy_config())

        await strategy.init()
        await strategy.on_start()
        for row in bars.iter_rows(named=True):
            session_open = datetime.datetime.combine(row["date"], datetime.time(9, 30))
            market_data.set_bar(row)
            wrapper.set_clock(session_open)
            await strategy.on_bar(
                session_open,
                {SYMBOL: _quote_payload(row)},
                FrameType.DAY,
            )
            asset = adapter.query_assets()
            positions = adapter.query_positions()
            shares = int(
                sum(float(position.shares) for position in positions if position.asset == SYMBOL)
            )
            cash = round(float(asset.cash if asset is not None else 0.0), 6)
            market_value = round(shares * float(row["close"]), 6)
            total = round(cash + market_value, 6)
            live_curve.append(
                {
                    "dt": row["date"].isoformat(),
                    "cash": cash,
                    "market_value": market_value,
                    "total": total,
                }
            )
            db.upsert_asset(
                Asset(
                    portfolio_id=portfolio_id,
                    dt=row["date"],
                    principal=INITIAL_CASH,
                    cash=cash,
                    frozen_cash=0.0,
                    market_value=market_value,
                    total=total,
                )
            )
        await strategy.on_stop()

        stats = metrics(
            portfolio_id,
            start=datetime.date.fromisoformat(baseline["data"]["scenario_start"]),
            end=datetime.date.fromisoformat(baseline["metrics"]["raw"]["end_date"]),
        )
        assert stats is not None
        return {
            "trades": _live_trade_facts(adapter.query_trades()),
            "equity_curve": live_curve,
            "metrics": _metrics_snapshot(stats),
        }


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.release_gate
async def test_dual_ma_parity_across_backtest_paper_and_live(calendar):
    _ = calendar
    baseline = _load_baseline()
    bars = _load_scenario_bars(baseline)
    expected_trades = _expected_trade_facts(baseline)
    expected_curve = _expected_equity_curve(baseline)
    expected_metrics = _expected_metrics(baseline)

    backtest_result = await _run_backtest_mode(baseline, ScenarioFeed(bars))
    paper_result = await _run_paper_mode(baseline, bars)
    live_result = await _run_live_mode(baseline, bars)

    assert backtest_result["trades"] == expected_trades
    assert paper_result["trades"] == expected_trades
    assert live_result["trades"] == expected_trades
    assert backtest_result["trades"] == paper_result["trades"] == live_result["trades"]

    assert backtest_result["equity_curve"] == expected_curve
    assert paper_result["equity_curve"] == expected_curve
    assert live_result["equity_curve"] == expected_curve
    assert backtest_result["equity_curve"] == paper_result["equity_curve"] == live_result["equity_curve"]

    assert backtest_result["metrics"] == expected_metrics
    assert paper_result["metrics"] == expected_metrics
    assert live_result["metrics"] == expected_metrics
    assert backtest_result["metrics"] == paper_result["metrics"] == live_result["metrics"]