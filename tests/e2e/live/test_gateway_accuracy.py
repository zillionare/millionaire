from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import polars as pl
import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import BrokerKind, FrameType, OrderSide
from quantide.core.ports import OrderRequest
from quantide.core.runtime.adapter_registry import AdapterRegistry
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
    GatewayTradeStateConsistencyError,
)
from quantide.core.runtime.gateway_client import GatewayClient
from quantide.core.runtime.registration import register_port_backed_broker
from quantide.data.sqlite import db
from quantide.service.registry import BrokerRegistry
from quantide.service.strategy_runtime import StrategyBrokerProxy
from quantide.strategies.example.dual_ma import DualMAStrategy
from tests.e2e.support.gateway_stub import (
    GatewayCancelScript,
    GatewayScenario,
    GatewaySubmitScript,
    running_gateway_stub,
)

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
LIVE_BASELINE_PATH = ASSETS_ROOT / "baselines" / "dual_ma_2024.live.json"
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
        return {
            symbol: QuoteSnapshot(
                symbol=symbol,
                price=float(self._current_bar["open"]),
                open=float(self._current_bar["open"]),
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


class StaticMarketData:
    def __init__(
        self,
        *,
        price: float,
        up_limit: float | None = None,
        down_limit: float | None = None,
    ):
        self._price = price
        self._up_limit = up_limit
        self._down_limit = down_limit

    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        return {
            symbol: QuoteSnapshot(
                symbol=symbol,
                price=self._price,
                open=self._price,
                high=self._price,
                low=self._price,
                volume=1000.0,
                amount=self._price * 1000,
                ts=datetime.datetime(2024, 1, 1, 9, 30),
            )
            for symbol in symbols
        }

    def get_price_limits(self, asset: str) -> tuple[float, float]:
        _ = asset
        return float(self._down_limit or 0.0), float(self._up_limit or 0.0)


def _load_live_baseline() -> dict[str, Any]:
    return json.loads(LIVE_BASELINE_PATH.read_text())


def _load_bars(end_date: datetime.date) -> pl.DataFrame:
    return (
        pl.read_parquet(MARKET_PATH)
        .with_columns(pl.col("date").dt.date())
        .filter((pl.col("asset") == SYMBOL) & (pl.col("date") <= end_date))
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


def _initial_asset(principal: float) -> dict[str, float]:
    return {
        "principal": principal,
        "total": principal,
        "cash": principal,
        "market_value": 0.0,
        "frozen_cash": 0.0,
    }


def _build_gateway_port(
    stub_base_url: str,
    market_data: Any,
) -> tuple[GatewayBrokerAdapter, GatewayBrokerWrapper, StrategyBrokerProxy]:
    client = GatewayClient(stub_base_url, username="u", password="p", timeout=2)
    adapter = GatewayBrokerAdapter(client)
    wrapper = GatewayBrokerWrapper(adapter)
    handle = register_port_backed_broker(
        registry=BrokerRegistry(),
        adapters=AdapterRegistry(),
        port=adapter,
        portfolio_id="gateway",
        kind=BrokerKind.QMT,
        legacy=wrapper,
    )
    return adapter, wrapper, StrategyBrokerProxy(handle, "dual-ma-live")


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_dual_ma_live_strategy_path_preserves_qtoid_and_updates_state(monkeypatch) -> None:
    baseline = _load_live_baseline()["strategy_full_fill"]
    trade_date = datetime.date.fromisoformat(baseline["trade_date"])
    bars = _load_bars(trade_date)
    market_data = ReplayMarketData(bars)
    row = bars.filter(pl.col("date") == trade_date).row(0, named=True)
    market_data.set_bar(row)
    scenario = GatewayScenario(
        asset=_initial_asset(200000.0),
        submit_scripts=[
            GatewaySubmitScript(
                side="buy",
                symbol=SYMBOL,
                response={"success": True, "order_id": baseline["external_order_id"]},
                order={
                    "symbol": SYMBOL,
                    "side": "buy",
                    "shares": baseline["shares"],
                    "price": baseline["price"],
                    "status": "filled",
                    "filled": baseline["shares"],
                    "time": f"{baseline['trade_date']} 09:30:00",
                },
                trades=[
                    {
                        "tid": "gw-live-fill-1",
                        "symbol": SYMBOL,
                        "side": "buy",
                        "shares": baseline["shares"],
                        "price": baseline["price"],
                        "amount": baseline["amount"],
                        "fee": baseline["fee"],
                        "time": f"{baseline['trade_date']} 09:30:05",
                    }
                ],
                asset_after=baseline["asset_after"],
                positions_after=baseline["positions_after"],
                expose_order_qtoid=False,
                expose_trade_qtoid=False,
            )
        ],
    )

    db.init(":memory:")
    from quantide.core.runtime import gateway_broker as _gb_mod
    monkeypatch.setattr(_gb_mod, "daily_bars", market_data)
    from quantide.service.livequote import live_quote
    live_quote._limits[SYMBOL] = {
        "up_limit": float(row["up_limit"]),
        "down_limit": float(row["down_limit"]),
    }
    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        adapter, _, broker = _build_gateway_port(stub.base_url, market_data)
        strategy = DualMAStrategy(
            broker,
            {
                "symbol": SYMBOL,
                "fast": 5,
                "slow": 10,
                "invest": 100000,
            },
        )
        with patch(
            "quantide.core.runtime.gateway_broker.uuid4",
            return_value=baseline["qtoid"],
        ):
            await strategy.on_bar(
                datetime.datetime.combine(trade_date, datetime.time(9, 30)),
                {SYMBOL: _quote_payload(row)},
                FrameType.DAY,
            )
        orders = adapter.query_orders()
        trades = adapter.query_trades(order_id=baseline["qtoid"])
        asset = adapter.query_assets()
        positions = adapter.query_positions()

    assert len(orders) == 1
    assert orders[0].order_id == baseline["qtoid"]
    assert orders[0].status == "filled"
    assert int(orders[0].shares) == baseline["shares"]
    assert round(float(orders[0].price), 6) == baseline["price"]
    assert len(trades) == 1
    assert trades[0].order_id == baseline["qtoid"]
    assert round(float(trades[0].amount), 6) == baseline["amount"]
    assert round(float(asset.cash), 6) == baseline["asset_after"]["cash"]
    assert round(float(asset.market_value), 6) == baseline["asset_after"]["market_value"]
    assert round(float(asset.total), 6) == baseline["asset_after"]["total"]
    assert len(positions) == 1
    assert positions[0].asset == SYMBOL
    assert int(positions[0].shares) == baseline["positions_after"][0]["shares"]
    assert round(float(positions[0].mv), 6) == baseline["positions_after"][0]["market_value"]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_live_gateway_partial_fill_then_cancel_keeps_state_single_applied() -> None:
    baseline = _load_live_baseline()["partial_cancel"]
    scenario = GatewayScenario(
        asset=_initial_asset(200000.0),
        submit_scripts=[
            GatewaySubmitScript(
                side="buy",
                symbol=SYMBOL,
                response={
                    "success": True,
                    "qtoid": baseline["qtoid"],
                    "order_id": baseline["external_order_id"],
                },
                order={
                    "symbol": SYMBOL,
                    "side": "buy",
                    "shares": baseline["requested_shares"],
                    "price": baseline["price"],
                    "status": "partial",
                    "filled": baseline["filled_shares"],
                    "time": "2026-05-13 09:32:00",
                },
                trades=[
                    {
                        "tid": "gw-partial-1",
                        "symbol": SYMBOL,
                        "side": "buy",
                        "shares": baseline["filled_shares"],
                        "price": baseline["price"],
                        "amount": baseline["amount"],
                        "fee": baseline["fee"],
                        "time": "2026-05-13 09:32:03",
                    }
                ],
                asset_after=baseline["asset_after"],
                positions_after=baseline["positions_after"],
            )
        ],
        cancel_scripts=[
            GatewayCancelScript(
                qtoid=baseline["qtoid"],
                response={"success": True, "qtoid": baseline["qtoid"]},
                order_status="cancelled",
            )
        ],
    )

    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        market_data = StaticMarketData(price=baseline["price"], up_limit=baseline["price"])
        client = GatewayClient(stub.base_url, username="u", password="p", timeout=2)
        adapter = GatewayBrokerAdapter(client)
        ack = await adapter.submit(
            OrderRequest(
                asset=SYMBOL,
                side=OrderSide.BUY,
                value=baseline["requested_shares"],
                price=baseline["price"],
                extra={"qtoid": baseline["qtoid"]},
            )
        )
        partial_orders = adapter.query_orders()
        partial_asset = adapter.query_assets()
        partial_positions = adapter.query_positions()
        cancel = await adapter.cancel(ack.order_id or "")
        cancelled_orders = adapter.query_orders(status="cancelled")
        repeated_asset = adapter.query_assets()

    assert ack.order_id == baseline["qtoid"]
    assert partial_orders[0].status == "partial"
    assert int(partial_orders[0].filled) == baseline["filled_shares"]
    assert cancel.success is True
    assert cancelled_orders[0].order_id == baseline["qtoid"]
    assert round(float(partial_asset.cash), 6) == baseline["asset_after"]["cash"]
    assert round(float(partial_asset.total), 6) == baseline["asset_after"]["total"]
    assert round(float(repeated_asset.total), 6) == baseline["asset_after"]["total"]
    assert int(partial_positions[0].shares) == baseline["positions_after"][0]["shares"]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_live_gateway_reject_leaves_queries_unchanged() -> None:
    baseline = _load_live_baseline()["reject"]
    scenario = GatewayScenario(asset=_initial_asset(200000.0), reject_next_orders=[baseline["error"]])

    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        market_data = StaticMarketData(price=10.0, up_limit=10.0)
        client = GatewayClient(stub.base_url, username="u", password="p", timeout=2)
        adapter = GatewayBrokerAdapter(client)
        ack = await adapter.submit(
            OrderRequest(
                asset=SYMBOL,
                side=OrderSide.BUY,
                value=100,
                price=10.0,
                extra={"qtoid": baseline["qtoid"]},
            )
        )

        asset = adapter.query_assets()
        positions = adapter.query_positions()
        orders = adapter.query_orders()
        trades = adapter.query_trades()

    assert ack.order_id is None
    assert ack.status == "rejected"
    assert baseline["error"] in ack.message
    assert round(float(asset.total), 6) == 200000.0
    assert positions == []
    assert orders == []
    assert trades == []


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_live_gateway_out_of_order_replay_recovers_qtoid_after_reconnect() -> None:
    baseline = _load_live_baseline()["out_of_order_replay"]
    scenario = GatewayScenario(
        asset=_initial_asset(100000.0),
        submit_scripts=[
            GatewaySubmitScript(
                side="buy",
                symbol=SYMBOL,
                response={"success": True, "order_id": baseline["external_order_id"]},
                order={
                    "symbol": SYMBOL,
                    "side": "buy",
                    "shares": baseline["shares"],
                    "price": baseline["price"],
                    "status": "filled",
                    "filled": baseline["shares"],
                    "time": "2026-05-13 10:00:00",
                },
                trades=[
                    {
                        "tid": "gw-replay-1",
                        "symbol": SYMBOL,
                        "side": "buy",
                        "shares": baseline["shares"],
                        "price": baseline["price"],
                        "amount": baseline["amount"],
                        "fee": baseline["fee"],
                        "time": "2026-05-13 10:00:03",
                    }
                ],
                asset_after=baseline["asset_after"],
                positions_after=baseline["positions_after"],
                expose_order_qtoid=False,
                expose_trade_qtoid=False,
            )
        ],
    )

    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        market_data = StaticMarketData(price=baseline["price"], up_limit=baseline["price"])
        first = GatewayBrokerAdapter(
            GatewayClient(stub.base_url, username="u", password="p", timeout=2),
        )
        ack = await first.submit(
            OrderRequest(
                asset=SYMBOL,
                side=OrderSide.BUY,
                value=baseline["shares"],
                price=baseline["price"],
                extra={"qtoid": baseline["qtoid"]},
            )
        )
        second = GatewayBrokerAdapter(
            GatewayClient(stub.base_url, username="u", password="p", timeout=2),
        )
        trades = second.query_trades(order_id=ack.order_id)
        orders = second.query_orders()
        asset_once = second.query_assets()
        asset_twice = second.query_assets()

    assert ack.order_id == baseline["qtoid"]
    assert trades[0].order_id == baseline["qtoid"]
    assert orders[0].order_id == baseline["qtoid"]
    assert round(float(asset_once.total), 6) == baseline["asset_after"]["total"]
    assert round(float(asset_twice.total), 6) == baseline["asset_after"]["total"]


def test_live_gateway_mapping_break_raises_block_candidate() -> None:
    baseline = _load_live_baseline()["mapping_break"]
    scenario = GatewayScenario(orders=baseline["orders"])

    with running_gateway_stub(prefix="/qmt", scenario=scenario) as stub:
        adapter = GatewayBrokerAdapter(
            GatewayClient(stub.base_url, username="u", password="p", timeout=2)
        )
        with pytest.raises(GatewayTradeStateConsistencyError):
            adapter.query_orders()
