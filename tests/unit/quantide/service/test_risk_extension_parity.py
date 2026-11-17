"""Backtest overlay and Paper risk-strategy parity for the teaching cap."""

from __future__ import annotations

import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import polars as pl
import pytest

from quantide.data.sqlite import db
from quantide.service.backtest_broker import BacktestBroker
from quantide.service.risk_programs import RiskProgramRegistry
from quantide.service.sim_broker import PaperBroker

ASSET = "000001.SZ"
TEMPLATE = (
    Path(__file__).resolve().parents[4]
    / "quantide"
    / "assets"
    / "examples"
    / "risk_single_asset_cap.py"
)


def _adapter():
    module = ModuleType("risk_cap_parity")
    module.__file__ = str(TEMPLATE)
    exec(compile(TEMPLATE.read_text(encoding="utf-8"), str(TEMPLATE), "exec"), module.__dict__)
    registry = RiskProgramRegistry()
    module.register_extensions(registry)
    adapter = registry.get("example.single_asset_weight_cap")
    assert adapter is not None
    return adapter


class _BacktestFeed:
    def __init__(self) -> None:
        self.match_data = pl.DataFrame(
            {
                "date": [datetime.date(2024, 1, 2)],
                "open": [10.0],
                "close": [10.0],
                "up_limit": [11.0],
                "down_limit": [9.0],
                "volume": [1_000_000_000.0],
            }
        )

    def get_price_for_match(self, asset, tm):
        return self.match_data

    def get_trade_price_limits(self, asset, dt):
        return 9.0, 11.0

    def get_close_factor(self, assets, start, end):
        return pl.DataFrame(
            [], schema={"dt": pl.Date, "asset": pl.Utf8, "close": pl.Float64, "factor": pl.Float64}
        )

    get_close_adjust_factor = get_close_factor


class _PaperMarketData:
    def snapshot(self, symbols):
        return {
            symbol: SimpleNamespace(
                price=10.0, open=10.0, high=10.0, low=10.0, volume=1_000_000_000.0, amount=1e10
            )
            for symbol in symbols
        }


@pytest.mark.asyncio
async def test_backtest_overlay_and_paper_strategy_clip_the_same_lot(calendar) -> None:
    adapter = _adapter()
    order_time = calendar.replace_time(datetime.date(2024, 1, 2), 9, 30)
    db.init(":memory:")

    backtest = BacktestBroker(
        bt_start=datetime.date(2024, 1, 2),
        bt_end=datetime.date(2024, 1, 10),
        portfolio_id="risk-cap-backtest",
        data_feed=_BacktestFeed(),
        principal=1_000_000,
        commission=0.0,
        min_commission=0.0,
        transfer_fee=0.0,
        stamp_duty=0.0,
    )
    overlay = adapter.overlay_factory(dict(adapter.default_params))
    await overlay.check_open(backtest, order_time)
    backtest_result = await backtest.buy(ASSET, 50_000, price=10.0, order_time=order_time)

    paper = PaperBroker(
        portfolio_id="risk-cap-paper",
        principal=1_000_000,
        commission=0.0,
        min_commission=0.0,
        stamp_tax=0.0,
        transfer_fee=0.0,
        market_data=_PaperMarketData(),
        market_value_update_interval=0.0,
    )
    try:
        paper.set_clock(order_time)
        paper._limits[ASSET] = {"down": 9.0, "up": 11.0}
        live = adapter.live_strategy_factory(paper, dict(adapter.default_params))
        await live.on_check(paper.positions, order_time)
        await paper.buy(ASSET, 50_000, price=10.0, timeout=0.01)
        paper_orders = db.get_orders(portfolio_id="risk-cap-paper")
    finally:
        paper.close()

    # 1,000,000 * 25% / 10 = 25,000 shares on both paths.
    assert [trade.shares for trade in backtest_result.trades] == [25_000]
    assert paper_orders["shares"].to_list() == [25_000]
