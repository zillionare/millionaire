"""B10-gateway-broker round 2: Additional missing-line tests for gateway_broker.py.

Targets lines NOT covered by test_v0204_b10_gateway_broker.py:
- get_history: qfq_adjustment path (153)
- GatewayBrokerWrapper.trade_target_pct: total_asset<=0 (516)
- GatewayBrokerWrapper._submit_legacy_order: ack.order_id is None (580)
- GatewayBrokerAdapter.trade_target_pct: asset_view None or total<=0 (873)
- GatewayBrokerAdapter.cancel_all: side mismatch continue (983)
- GatewayBrokerAdapter.query_assets: empty row -> None (1012)
- GatewayBrokerAdapter._resolve_sizing_price: up_limit (1096), down_limit (1098)
- GatewayBrokerAdapter._resolve_shares: shares style (1103-1104), price<=0 (1106),
  amount style (1107-1108), percent asset None (1110-1112), target_pct (1115-1132)
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

import quantide.core.runtime.gateway_broker as gb_mod
from quantide.core.enums import OrderSide
from quantide.core.ports import AssetView, OrderRequest, PositionView
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
)


def _make_wrapper() -> GatewayBrokerWrapper:
    """Build a GatewayBrokerWrapper with a dummy adapter."""
    wrapper = GatewayBrokerWrapper(MagicMock(spec=GatewayBrokerAdapter))  # type: ignore[arg-type]
    return wrapper


# ---------------------------------------------------------------------------
# get_history: qfq_adjustment path (153)
# ---------------------------------------------------------------------------


def test_get_history_applies_qfq_when_no_forming_bar_and_adjust_present():
    """[AC-NFR1101-01] get_history calls qfq_adjustment when not forming_applied and adjust present (line 153)."""
    wrapper = _make_wrapper()
    wrapper._history_provider = None
    hist = pl.DataFrame({
        "date": [dt.date(2024, 1, 1)],
        "asset": ["A"],
        "open": [10.0],
        "high": [11.0],
        "low": [9.0],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
        "adjust": [1.0],
        "is_st": [False],
        "up_limit": [11.0],
        "down_limit": [9.0],
    })
    # include_forming_bar=False -> forming_applied stays False -> qfq path (line 153)
    end_dt = dt.datetime(2024, 1, 2, 10, 0)
    with patch.object(wrapper, "_resolve_history_end_date", return_value=dt.date(2024, 1, 2)), \
         patch.object(wrapper, "_provider_get_bars", return_value=hist) as mock_get, \
         patch.object(gb_mod, "qfq_adjustment", side_effect=lambda df, **kw: df) as mock_qfq:
        result = wrapper.get_history("A", 5, end_dt, "1d", include_forming_bar=False)
    mock_get.assert_called_once()
    mock_qfq.assert_called_once()
    assert result is hist


# ---------------------------------------------------------------------------
# GatewayBrokerWrapper.trade_target_pct: total_asset <= 0 (516)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrapper_trade_target_pct_returns_empty_when_total_le_zero():
    """[AC-NFR1101-01] trade_target_pct returns empty when total_asset<=0 (line 516)."""
    wrapper = _make_wrapper()
    # asset.total = 0 -> total_asset <= 0
    mock_asset = MagicMock()
    mock_asset.total = 0
    with patch.object(GatewayBrokerWrapper, "asset", new_callable=lambda: mock_asset), \
         patch.object(GatewayBrokerWrapper, "positions", new_callable=lambda: {}):
        result = await wrapper.trade_target_pct("A", 0.5)
    from quantide.core.ports.broker import ExecutionResult
    assert result == ExecutionResult.empty()


# ---------------------------------------------------------------------------
# GatewayBrokerWrapper._submit_legacy_order: ack.order_id is None (580)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_legacy_order_returns_empty_when_order_id_none():
    """[AC-NFR1101-01] _submit_legacy_order returns empty when ack.order_id is None (line 580)."""
    wrapper = _make_wrapper()
    wrapper._strategy_cheat_on_close = True  # skip deferred path
    mock_ack = MagicMock()
    mock_ack.order_id = None
    mock_ack.trades = []
    with patch.object(wrapper._adapter, "submit", new_callable=AsyncMock, return_value=mock_ack):
        result = await wrapper._submit_legacy_order(
            asset="A",
            side=OrderSide.BUY,
            value=100,
            style="shares",
            price=10.0,
            order_time=None,
            timeout=0.5,
            extra={},
        )
    from quantide.core.ports.broker import ExecutionResult
    assert result == ExecutionResult.empty()


# ---------------------------------------------------------------------------
# GatewayBrokerAdapter.trade_target_pct: asset_view None or total<=0 (873)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_trade_target_pct_returns_empty_when_asset_view_none():
    """[AC-NFR1101-01] adapter trade_target_pct returns empty when asset_view is None (line 873)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    with patch.object(adapter, "query_assets", return_value=None):
        result = await adapter.trade_target_pct("A", 0.5)
    from quantide.core.ports.broker import ExecutionResult
    assert result == ExecutionResult.empty()


@pytest.mark.asyncio
async def test_adapter_trade_target_pct_returns_empty_when_total_le_zero():
    """[AC-NFR1101-01] adapter trade_target_pct returns empty when total<=0 (line 873)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    asset_view = AssetView(cash=0, total=0, market_value=0, frozen_cash=0, principal=0, dt=dt.date.today())
    with patch.object(adapter, "query_assets", return_value=asset_view):
        result = await adapter.trade_target_pct("A", 0.5)
    from quantide.core.ports.broker import ExecutionResult
    assert result == ExecutionResult.empty()


# ---------------------------------------------------------------------------
# GatewayBrokerAdapter.cancel_all: side mismatch continue (983)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_cancel_all_continues_on_side_mismatch():
    """[AC-NFR1101-01] cancel_all continues when order side doesn't match (line 983)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    # Two orders: one BUY, one SELL; cancel_all(side=SELL) should skip the BUY one
    order_buy = MagicMock()
    order_buy.order_id = "o1"
    order_buy.side = "buy"
    order_sell = MagicMock()
    order_sell.order_id = "o2"
    order_sell.side = "sell"
    with patch.object(adapter, "query_orders", return_value=[order_buy, order_sell]), \
         patch.object(adapter, "cancel", new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = MagicMock(success=True)
        count = await adapter.cancel_all(side=OrderSide.SELL)
    # Only the sell order should have been cancelled
    assert count == 1
    mock_cancel.assert_awaited_once_with("o2")


# ---------------------------------------------------------------------------
# GatewayBrokerAdapter.query_assets: empty row -> None (1012)
# ---------------------------------------------------------------------------


def test_adapter_query_assets_returns_none_when_empty_row():
    """[AC-NFR1101-01] query_assets returns None when row is empty (line 1012)."""
    client = MagicMock()
    client.get_json.return_value = {}
    adapter = GatewayBrokerAdapter(client)
    result = adapter.query_assets()
    assert result is None


# ---------------------------------------------------------------------------
# GatewayBrokerAdapter._resolve_sizing_price: up_limit (1096), down_limit (1098)
# ---------------------------------------------------------------------------


def test_resolve_sizing_price_returns_up_limit_for_buy():
    """[AC-NFR1101-01] _resolve_sizing_price returns up_limit for BUY (line 1096)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=100,
        style="shares",
        price=0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    with patch.object(gb_mod.live_quote, "get_price_limits", return_value=(9.0, 11.0)):
        result = adapter._resolve_sizing_price(request, execution_price=10.0)
    assert result == 11.0


def test_resolve_sizing_price_returns_down_limit_for_sell():
    """[AC-NFR1101-01] _resolve_sizing_price returns down_limit for SELL (line 1098)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.SELL,
        value=100,
        style="shares",
        price=0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    with patch.object(gb_mod.live_quote, "get_price_limits", return_value=(9.0, 11.0)):
        result = adapter._resolve_sizing_price(request, execution_price=10.0)
    assert result == 9.0


# ---------------------------------------------------------------------------
# GatewayBrokerAdapter._resolve_shares: shares style (1103-1104), price<=0 (1106),
# amount style (1107-1108), percent asset None (1110-1112), target_pct (1115-1132)
# ---------------------------------------------------------------------------


def test_resolve_shares_shares_style_floors_to_lot():
    """[AC-NFR1101-01] _resolve_shares returns floored shares for 'shares' style (1103-1104)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=250,
        style="shares",
        price=10.0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    assert adapter._resolve_shares(request, 10.0) == 200


def test_resolve_shares_returns_zero_when_price_le_zero():
    """[AC-NFR1101-01] _resolve_shares returns 0 when price<=0 (line 1106)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=1000,
        style="amount",
        price=0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    assert adapter._resolve_shares(request, 0.0) == 0


def test_resolve_shares_amount_style_computes_shares():
    """[AC-NFR1101-01] _resolve_shares computes shares for 'amount' style (1107-1108)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=1000,
        style="amount",
        price=10.0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    # 1000 / 10 = 100, floored to 100
    assert adapter._resolve_shares(request, 10.0) == 100


def test_resolve_shares_percent_style_returns_zero_when_asset_none():
    """[AC-NFR1101-01] _resolve_shares returns 0 for 'percent' style when asset is None (1110-1112)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=0.5,
        style="percent",
        price=10.0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    with patch.object(adapter, "query_assets", return_value=None):
        assert adapter._resolve_shares(request, 10.0) == 0


def test_resolve_shares_target_pct_buy_delta_le_zero_returns_zero():
    """[AC-NFR1101-01] _resolve_shares target_pct BUY returns 0 when delta<=0 (1127-1128)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.BUY,
        value=0.1,
        style="target_pct",
        price=10.0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    asset_view = AssetView(cash=100000, total=100000, market_value=0, frozen_cash=0, principal=100000, dt=dt.date.today())
    # position with shares 2000, price 10 -> current_value 20000, target 10000 -> delta -10000 <= 0
    pos = PositionView(asset="A", shares=2000, avail=2000, price=10.0, mv=20000.0, dt=dt.date.today())
    with patch.object(adapter, "query_assets", return_value=asset_view), \
         patch.object(adapter, "query_positions", return_value=[pos]):
        assert adapter._resolve_shares(request, 10.0) == 0


def test_resolve_shares_target_pct_sell_delta_ge_zero_returns_zero():
    """[AC-NFR1101-01] _resolve_shares target_pct SELL returns 0 when delta>=0 (1130-1131)."""
    adapter = GatewayBrokerAdapter(MagicMock())
    request = OrderRequest(
        asset="A",
        side=OrderSide.SELL,
        value=0.5,
        style="target_pct",
        price=10.0,
        order_time=None,
        timeout=0.5,
        extra={},
    )
    asset_view = AssetView(cash=100000, total=100000, market_value=0, frozen_cash=0, principal=100000, dt=dt.date.today())
    # No position -> current_value 0, target 50000 -> delta 50000 >= 0 -> SELL returns 0
    with patch.object(adapter, "query_assets", return_value=asset_view), \
         patch.object(adapter, "query_positions", return_value=[]):
        assert adapter._resolve_shares(request, 10.0) == 0
