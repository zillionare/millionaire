"""Generate the minimal E2E accuracy-contract demo baseline.

The demo intentionally uses an independent ledger instead of BacktestRunner so it
can act as a reviewable oracle for the release-gate scenario.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

ASSET = "000001.SZ"
START_DATE = dt.date(2024, 1, 2)
END_DATE = dt.date(2024, 5, 31)
FAST_WINDOW = 5
SLOW_WINDOW = 10
INITIAL_CASH = 200_000.0
INVEST_AMOUNT = 100_000.0
COMMISSION = 0.0005


@dataclass(frozen=True)
class DemoTrade:
    """A single expected trade in the demo scenario."""

    trade_date: str
    signal_date: str
    side: str
    shares: int
    price: float
    amount: float
    fee: float
    cash_after: float
    position_after: int
    market_value_after: float
    total_after: float
    prev_fast: float
    prev_slow: float
    curr_fast: float
    curr_slow: float


def _read_demo_bars(path: Path) -> pd.DataFrame:
    """Read and normalize the demo asset bars.

    Args:
        path: Parquet file with extended daily bar columns.

    Returns:
        A pandas DataFrame sorted by date.
    """
    frame = (
        pl.read_parquet(path)
        .filter(pl.col("asset") == ASSET)
        .with_columns(pl.col("date").dt.date())
        .sort("date")
    )
    result = frame.to_pandas()
    result["date"] = pd.to_datetime(result["date"]).dt.date
    return result


def _round_float(value: float) -> float:
    """Round floats for stable JSON output."""
    return round(float(value), 6)


def _trade_record(
    row: Any,
    signal_date: dt.date,
    side: str,
    shares: int,
    cash_after: float,
    position_after: int,
    averages: tuple[float, float, float, float],
) -> DemoTrade:
    """Build a rounded trade record."""
    amount = shares * float(row.open)
    fee = amount * COMMISSION
    market_value = position_after * float(row.close)
    return DemoTrade(
        trade_date=str(row.date),
        signal_date=str(signal_date),
        side=side,
        shares=shares,
        price=_round_float(row.open),
        amount=_round_float(amount),
        fee=_round_float(fee),
        cash_after=_round_float(cash_after),
        position_after=position_after,
        market_value_after=_round_float(market_value),
        total_after=_round_float(cash_after + market_value),
        prev_fast=_round_float(averages[0]),
        prev_slow=_round_float(averages[1]),
        curr_fast=_round_float(averages[2]),
        curr_slow=_round_float(averages[3]),
    )


def _calculate_metrics(equity: pd.DataFrame) -> dict[str, Any]:
    """Calculate the demo metrics with explicit formulas.

    Args:
        equity: Daily equity ledger indexed by date.

    Returns:
        Raw and formatted metric values.
    """
    returns = equity["total"].pct_change().dropna()
    total_return = (1 + returns).prod() - 1
    years = len(returns) / 252
    cagr = (1 + total_return) ** (1 / years) - 1
    volatility = returns.std() * np.sqrt(252)
    sharpe = returns.mean() / returns.std() * np.sqrt(252)
    cumulative = (1 + returns).cumprod()
    drawdown = (
        cumulative - cumulative.expanding().max()
    ) / cumulative.expanding().max()
    return {
        "raw": {
            "start_date": str(returns.index.min()),
            "end_date": str(returns.index.max()),
            "trading_days": int(len(returns)),
            "ending_total": _round_float(equity["total"].iloc[-1]),
            "total_return": _round_float(total_return),
            "cagr": _round_float(cagr),
            "volatility_ann": _round_float(volatility),
            "sharpe_ratio": _round_float(sharpe),
            "max_drawdown": _round_float(drawdown.min()),
        },
        "formatted": {
            "Total Return": f"{total_return:.2%}",
            "CAGR": f"{cagr:.2%}",
            "Volatility (ann.)": f"{volatility:.2%}",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "Max Drawdown": f"{drawdown.min():.2%}",
        },
    }


def _serialize_equity(equity: pd.DataFrame) -> list[dict[str, Any]]:
    """Serialize the daily equity ledger for downstream tests.

    Args:
        equity: Daily equity ledger indexed by date.

    Returns:
        JSON-serializable equity rows.
    """
    rows: list[dict[str, Any]] = []
    for row in equity.reset_index().itertuples(index=False):
        rows.append(
            {
                "dt": str(row.date),
                "cash": _round_float(row.cash),
                "shares": int(row.shares),
                "close": _round_float(row.close),
                "market_value": _round_float(row.market_value),
                "total": _round_float(row.total),
            }
        )
    return rows


def simulate(path: Path) -> dict[str, Any]:
    """Run the independent dual-MA demo simulation.

    Args:
        path: Extended daily bar Parquet fixture.

    Returns:
        JSON-serializable scenario baseline.
    """
    source_frame = pl.read_parquet(path)
    bars = _read_demo_bars(path)
    scenario_bars = bars[(bars["date"] >= START_DATE) & (bars["date"] <= END_DATE)]
    all_dates = list(bars["date"])

    cash = INITIAL_CASH
    shares = 0
    trades: list[DemoTrade] = []
    equity_rows: list[dict[str, Any]] = []

    for row in scenario_bars.itertuples(index=False):
        previous_dates = [date for date in all_dates if date < row.date]
        history = bars[bars["date"].isin(previous_dates)].tail(SLOW_WINDOW + 5)
        if len(history) >= SLOW_WINDOW + 2:
            closes = history["close"].to_numpy()
            curr_fast = closes[-FAST_WINDOW:].mean()
            curr_slow = closes[-SLOW_WINDOW:].mean()
            prev_fast = closes[-(FAST_WINDOW + 1) : -1].mean()
            prev_slow = closes[-(SLOW_WINDOW + 1) : -1].mean()
            averages = (prev_fast, prev_slow, curr_fast, curr_slow)
            signal_date = previous_dates[-1]

            if prev_fast <= prev_slow and curr_fast > curr_slow and shares == 0:
                quantity = (
                    int(
                        (INVEST_AMOUNT / (float(row.up_limit) * (1 + COMMISSION)))
                        // 100
                    )
                    * 100
                )
                amount = quantity * float(row.open)
                fee = amount * COMMISSION
                cash -= amount + fee
                shares += quantity
                trades.append(
                    _trade_record(
                        row, signal_date, "BUY", quantity, cash, shares, averages
                    )
                )
            elif prev_fast >= prev_slow and curr_fast < curr_slow and shares > 0:
                quantity = shares
                amount = quantity * float(row.open)
                fee = amount * COMMISSION
                cash += amount - fee
                shares = 0
                trades.append(
                    _trade_record(
                        row, signal_date, "SELL", quantity, cash, shares, averages
                    )
                )

        equity_rows.append(
            {
                "date": row.date,
                "cash": cash,
                "shares": shares,
                "close": float(row.close),
                "market_value": shares * float(row.close),
                "total": cash + shares * float(row.close),
            }
        )

    equity = pd.DataFrame(equity_rows).set_index("date")
    schema = {
        name: str(dtype)
        for name, dtype in zip(source_frame.columns, source_frame.dtypes, strict=True)
    }
    return {
        "data": {
            "source": str(path),
            "asset": ASSET,
            "fixture_columns": schema,
            "fixture_asset_count": int(source_frame.select("asset").n_unique()),
            "fixture_date_min": str(source_frame.select(pl.col("date").min()).item()),
            "fixture_date_max": str(source_frame.select(pl.col("date").max()).item()),
            "scenario_start": str(START_DATE),
            "scenario_end": str(END_DATE),
            "scenario_rows": int(len(scenario_bars)),
        },
        "strategy": {
            "name": "DualMAStrategy",
            "fast": FAST_WINDOW,
            "slow": SLOW_WINDOW,
            "invest": INVEST_AMOUNT,
            "initial_cash": INITIAL_CASH,
            "commission": COMMISSION,
            "buy_quantity_rule": "floor(invest / (up_limit * (1 + commission)) / 100) * 100",
            "match_rule": "market order at same-day open after previous-day signal",
        },
        "equity_curve": _serialize_equity(equity),
        "trades": [asdict(trade) for trade in trades],
        "metrics": _calculate_metrics(equity),
        "stub_contract": {
            "tushare_stub": [
                "trade_cal returns baseline_calendar for the scenario window",
                "daily returns 2024_bars_ext_cols open/high/low/close/volume/amount",
                "adj_factor returns adjust for the same asset/date keys",
                "stk_limit returns up_limit/down_limit for the same asset/date keys",
                "stock_st returns is_st rows; missing rows mean false for this asset",
            ],
            "gateway_stub": [
                "quote stream replays the scenario rows in date order",
                "paper/live matching uses the same open price and limit-price fields",
                "order acknowledgements preserve qtoid and include an external_order_id only as mapping data",
                "fills match the baseline trade_date, side, shares, price, amount, and fee",
            ],
        },
    }


def main() -> None:
    """Run the command-line demo."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bars",
        type=Path,
        default=Path("tests/assets/2024_bars_ext_cols.parquet"),
    )
    args = parser.parse_args()
    print(json.dumps(simulate(args.bars), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
