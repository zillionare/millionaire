"""Regression coverage for interface issues found during the mypy review."""

from __future__ import annotations

import asyncio
import datetime

import pytest
from fasthtml.common import Div

from quantide.core.enums import BrokerKind
from quantide.core.runtime.port_broker import PortBackedBroker
from quantide.core.strategy import BaseStrategy
from quantide.service.backtest_orders import BacktestOrders
from quantide.service.paper_orders import _validate_paper_order_options
from quantide.service.shadow_broker import ShadowBroker
from quantide.service.sim_broker import PaperBroker
from quantide.web.layouts.main import MainLayout


def test_cancel_all_orders_accepts_legacy_none_return() -> None:
    """R1: a legacy broker returning None must not turn into a TypeError."""
    strategy = BaseStrategy(object.__new__(BacktestOrders), {})
    assert asyncio.run(strategy.cancel_all_orders()) == 0


def test_main_layout_preserves_subclass_main_block_override() -> None:
    """R4: subclasses may keep overriding main_block while instances can replace it."""

    class CustomLayout(MainLayout):
        def main_block(self):
            return "CUSTOM-CONTENT"

    layout = CustomLayout(title="review")
    assert layout._resolve_main_content() == "CUSTOM-CONTENT"
    layout.set_main_block(lambda: "INSTANCE-CONTENT")
    assert layout._resolve_main_content() == "INSTANCE-CONTENT"


def test_main_layout_allows_super_main_block_composition() -> None:
    """S3: subclasses may extend the base body through super().main_block()."""

    class ComposedLayout(MainLayout):
        def main_block(self):
            return super().main_block()

    content = ComposedLayout(title="review")._resolve_main_content()
    assert "review" in str(content)
    assert "这是页面的主要内容区域。" in str(content)

    layout = MainLayout(title="review")
    layout.main_block = Div("DIRECT-CONTENT")
    assert "DIRECT-CONTENT" in str(layout._resolve_main_content())


@pytest.mark.asyncio
async def test_port_backed_paper_broker_rejects_next_open_fill_timing() -> None:
    """R3: unsupported execution options fail explicitly instead of deeper in the call."""
    handle = PortBackedBroker(object.__new__(PaperBroker), "review", BrokerKind.SIMULATION)
    with pytest.raises(ValueError, match="fill_timing"):
        await handle.buy("000001.SZ", 100, fill_timing="next_open")


def test_paper_order_options_accept_immediate_fill_timing_and_strategy_id() -> None:
    """R3: immediate fill modes remain valid and attribution is a harmless no-op."""
    _validate_paper_order_options({"fill_timing": "close", "strategy_id": "review"})
    with pytest.raises(ValueError, match="order options"):
        _validate_paper_order_options({"unknown": True})


def _shadow_broker_with_known_prices(close_a: float) -> ShadowBroker:
    broker = ShadowBroker(
        portfolio_id="shadow",
        principal=10_000.0,
        config={
            "commission": 0.0,
            "stamp_duty": 0.0,
            "transfer_fee": 0.0,
            "min_commission": 0.0,
            "slippage_pct": 0.0,
            "fill_timing": "next_open",
        },
        trade_date=datetime.date(2026, 1, 5),
        cash=10_000.0,
        positions=[
            {
                "asset": "000001.SZ",
                "shares": 1_000,
                "avail": 1_000,
                "price": 10.0,
                "mv": 10_000.0,
            }
        ],
    )
    broker._price_cache.update({"000001.SZ": close_a, "000002.SZ": 10.0})
    broker._open_cache.update({"000001.SZ": 10.0, "000002.SZ": 10.0})
    broker._limit_cache.update({"000001.SZ": (0.0, 0.0), "000002.SZ": (0.0, 0.0)})
    return broker


@pytest.mark.parametrize("close_a", [10.0, 20.0])
def test_shadow_buy_percent_sizes_with_execution_price(close_a: float) -> None:
    """S1: next-open percentage sizing must not depend on the day's close."""
    broker = _shadow_broker_with_known_prices(close_a)
    result = asyncio.run(
        broker.buy_percent(
            "000002.SZ",
            0.1,
            order_time=datetime.datetime(2026, 1, 5, 9, 25),
        )
    )
    assert result.trades[0].shares == 200
    assert broker.total_assets == pytest.approx(8_000 + 1_000 * close_a + 200 * 10)


@pytest.mark.parametrize("close_a", [10.0, 20.0])
def test_shadow_trade_target_sizes_with_execution_price(close_a: float) -> None:
    """S1: target-percentage orders must not depend on the day's close."""
    broker = _shadow_broker_with_known_prices(close_a)
    result = asyncio.run(
        broker.trade_target_pct(
            "000002.SZ",
            0.1,
            order_time=datetime.datetime(2026, 1, 5, 9, 25),
        )
    )
    assert result.trades[0].shares == 200
    assert broker.total_assets == pytest.approx(8_000 + 1_000 * close_a + 200 * 10)
