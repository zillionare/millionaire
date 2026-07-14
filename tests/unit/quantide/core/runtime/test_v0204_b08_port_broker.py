"""B08-port-broker-1: Tests for quantide/core/runtime/port_broker.py.

Target: raise coverage from 70% to >=80%.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantide.core.enums import BidType, BrokerKind, OrderSide, OrderStatus
from quantide.core.runtime.port_broker import PortBackedBroker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_broker_port(
    asset_view=None,
    position_view=None,
    order_view=None,
):
    """Build a fake BrokerPort that returns canned views."""
    port = MagicMock()
    port.query_assets.return_value = asset_view
    port.query_positions.return_value = position_view or []
    port.query_orders.return_value = order_view or []
    return port


def _make_asset_view():
    v = MagicMock()
    v.dt = datetime.date(2024, 1, 1)
    v.principal = 100000.0
    v.cash = 50000.0
    v.frozen_cash = 0.0
    v.market_value = 50000.0
    v.total = 100000.0
    return v


def _make_position_view(asset: str = "000001.SZ"):
    v = MagicMock()
    v.asset = asset
    v.dt = datetime.date(2024, 1, 1)
    v.shares = 100.0
    v.avail = 100.0
    v.price = 10.0
    v.mv = 1000.0
    return v


def _make_order_view(
    asset: str = "000001.SZ",
    side: str = "buy",
    status: str = "FILLED",
    qtoid: str = "qt-1",
):
    v = MagicMock()
    v.asset = asset
    v.side = side
    v.shares = 100.0
    v.tm = datetime.datetime(2024, 1, 1, 10)
    v.price = 10.0
    v.filled = 100.0
    v.order_id = qtoid
    v.status = status
    v.error = ""
    return v


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_with_broker_kind_enum():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p-1", BrokerKind.SIMULATION)
    assert b.port is port
    assert b.portfolio_id == "p-1"
    assert b.kind == BrokerKind.SIMULATION
    assert b.portfolio_name == "p-1"  # default
    assert b.status is True


def test_init_with_string_kind_coerced():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p-2", "sim")
    assert b.kind == BrokerKind.SIMULATION


def test_init_with_explicit_portfolio_name():
    port = _make_broker_port()
    b = PortBackedBroker(
        port, "p-3", BrokerKind.BACKTEST,
        portfolio_name="My Account",
    )
    assert b.portfolio_name == "My Account"


def test_init_is_connected_defaults_to_status():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION, status=False)
    assert b.is_connected is False  # defaults to status when is_connected=None


def test_init_is_connected_overrides_status():
    port = _make_broker_port()
    b = PortBackedBroker(
        port, "p", BrokerKind.SIMULATION,
        status=True, is_connected=False,
    )
    assert b.is_connected is False


# ---------------------------------------------------------------------------
# asset / cash / principal / total_assets
# ---------------------------------------------------------------------------


def test_asset_uses_port_view_when_available():
    port = _make_broker_port(asset_view=_make_asset_view())
    b = PortBackedBroker(port, "p", BrokerKind.BACKTEST)
    asset = b.asset
    assert asset.cash == 50000.0
    assert asset.total == 100000.0


def test_asset_defaults_when_port_view_none():
    port = _make_broker_port(asset_view=None)
    b = PortBackedBroker(port, "p", BrokerKind.BACKTEST)
    asset = b.asset
    # Defaults to today / 0.0 values.
    assert asset.cash == 0.0
    assert asset.principal == 0.0
    assert asset.total == 0.0


def test_cash_returns_asset_cash():
    port = _make_broker_port(asset_view=_make_asset_view())
    b = PortBackedBroker(port, "p", BrokerKind.BACKTEST)
    assert b.cash == 50000.0


def test_principal_returns_asset_principal():
    port = _make_broker_port(asset_view=_make_asset_view())
    b = PortBackedBroker(port, "p", BrokerKind.BACKTEST)
    assert b.principal == 100000.0


def test_total_assets_returns_asset_total():
    port = _make_broker_port(asset_view=_make_asset_view())
    b = PortBackedBroker(port, "p", BrokerKind.BACKTEST)
    assert b.total_assets == 100000.0


# ---------------------------------------------------------------------------
# positions
# ---------------------------------------------------------------------------


def test_positions_returns_dict_from_port_view():
    views = [_make_position_view("000001.SZ"), _make_position_view("600000.SH")]
    port = _make_broker_port(position_view=views)
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    positions = b.positions
    assert isinstance(positions, dict)
    assert "000001.SZ" in positions
    assert "600000.SH" in positions


def test_positions_empty_when_no_views():
    port = _make_broker_port(position_view=[])
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b.positions == {}


# ---------------------------------------------------------------------------
# orders
# ---------------------------------------------------------------------------


def test_orders_calls_port_query_orders():
    port = _make_broker_port(order_view=[_make_order_view()])
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    orders = b.orders
    assert len(orders) == 1
    assert port.query_orders.called


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------


def test_record_delegates_to_port():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    b.record("k", 1.5, dt=datetime.datetime(2024, 1, 1), extra={"a": 1})
    port.record.assert_called_once()


# ---------------------------------------------------------------------------
# set_clock
# ---------------------------------------------------------------------------


def test_set_clock_no_broker_attribute_no_op():
    """When port has no _broker attribute, set_clock is a no-op."""
    port = MagicMock(spec=[])
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    b.set_clock(datetime.datetime(2024, 1, 1))  # no raise


def test_set_clock_with_broker_set_clock_calls_inner():
    inner = MagicMock()
    inner.set_clock = MagicMock()
    port = MagicMock()
    port._broker = inner
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    b.set_clock(datetime.datetime(2024, 1, 1))
    inner.set_clock.assert_called_once()


def test_set_clock_no_inner_set_clock_method():
    """Inner broker exists but has no set_clock method."""
    port = MagicMock()
    port._broker = MagicMock(spec=[])  # no set_clock method
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    b.set_clock(datetime.datetime(2024, 1, 1))  # no raise


# ---------------------------------------------------------------------------
# buy / sell / cancel / cancel_all / buy_percent / sell_percent /
# buy_amount / sell_amount / trade_target_pct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_forwards_to_port():
    port = _make_broker_port()
    port.buy = AsyncMock(return_value="buy-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.buy("000001.SZ", 100, price=10.0)
    assert res == "buy-resp"
    port.buy.assert_awaited()


@pytest.mark.asyncio
async def test_sell_forwards_to_port():
    port = _make_broker_port()
    port.sell = AsyncMock(return_value="sell-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.sell("000001.SZ", 100, price=10.0)
    assert res == "sell-resp"


@pytest.mark.asyncio
async def test_buy_percent_forwards():
    port = _make_broker_port()
    port.buy_percent = AsyncMock(return_value="bp-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.buy_percent("000001.SZ", 50.0)
    assert res == "bp-resp"


@pytest.mark.asyncio
async def test_buy_amount_forwards():
    port = _make_broker_port()
    port.buy_amount = AsyncMock(return_value="ba-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.buy_amount("000001.SZ", 5000.0)
    assert res == "ba-resp"


@pytest.mark.asyncio
async def test_sell_percent_forwards():
    port = _make_broker_port()
    port.sell_percent = AsyncMock(return_value="sp-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.sell_percent("000001.SZ", 50.0)
    assert res == "sp-resp"


@pytest.mark.asyncio
async def test_sell_amount_forwards():
    port = _make_broker_port()
    port.sell_amount = AsyncMock(return_value="sa-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.sell_amount("000001.SZ", 5000.0)
    assert res == "sa-resp"


@pytest.mark.asyncio
async def test_trade_target_pct_forwards():
    port = _make_broker_port()
    port.trade_target_pct = AsyncMock(return_value="tp-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.trade_target_pct("000001.SZ", 50.0)
    assert res == "tp-resp"


@pytest.mark.asyncio
async def test_cancel_order_forwards():
    port = _make_broker_port()
    port.cancel = AsyncMock(return_value="cancel-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.cancel_order("qt-1")
    assert res == "cancel-resp"


@pytest.mark.asyncio
async def test_cancel_all_orders_forwards():
    port = _make_broker_port()
    port.cancel_all = AsyncMock(return_value="cancel-all-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.cancel_all_orders(side=OrderSide.BUY)
    assert res == "cancel-all-resp"


@pytest.mark.asyncio
async def test_cancel_all_orders_with_none_side():
    port = _make_broker_port()
    port.cancel_all = AsyncMock(return_value="cancel-all-resp")
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    res = await b.cancel_all_orders()
    assert res == "cancel-all-resp"


# ---------------------------------------------------------------------------
# get_position
# ---------------------------------------------------------------------------


def test_get_position_returns_position_when_present():
    views = [_make_position_view("000001.SZ")]
    port = _make_broker_port(position_view=views)
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    pos = b.get_position("000001.SZ")
    assert pos is not None
    assert pos.asset == "000001.SZ"


def test_get_position_returns_none_when_absent():
    port = _make_broker_port(position_view=[])
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b.get_position("000999.SZ") is None


# ---------------------------------------------------------------------------
# _to_order / _to_side / _to_status (private helpers)
# ---------------------------------------------------------------------------


def test_to_side_passes_through_order_side_enum():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_side(OrderSide.BUY) == OrderSide.BUY
    assert b._to_side(OrderSide.SELL) == OrderSide.SELL


def test_to_side_converts_int_to_enum():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    # OrderSide.BUY.value might be 1, SELL 2 etc. Pass that int.
    buy_int = OrderSide.BUY.value
    assert b._to_side(buy_int) == OrderSide.BUY


def test_to_side_handles_unknown_int():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_side(9999) == OrderSide.UNKNOWN


def test_to_side_buy_chinese():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_side("买入") == OrderSide.BUY


def test_to_side_sell_chinese():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_side("卖出") == OrderSide.SELL


def test_to_side_unknown_string():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_side("xxx") == OrderSide.UNKNOWN


def test_to_status_passes_through_enum():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_status(OrderStatus.SUCCEEDED) == OrderStatus.SUCCEEDED


def test_to_status_int_known():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    int_value = OrderStatus.SUCCEEDED.value
    assert b._to_status(int_value) == OrderStatus.SUCCEEDED


def test_to_status_int_unknown_returns_unknown():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_status(99999) == OrderStatus.UNKNOWN


def test_to_status_string_aliases():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_status("SUBMITTED") == OrderStatus.REPORTED
    assert b._to_status("REJECTED") == OrderStatus.JUNK
    assert b._to_status("CANCELED") == OrderStatus.CANCELED
    assert b._to_status("CANCELLED") == OrderStatus.CANCELED
    assert b._to_status("PARTIAL") == OrderStatus.PART_SUCC
    assert b._to_status("FILLED") == OrderStatus.SUCCEEDED
    assert b._to_status("SUCCEEDED") == OrderStatus.SUCCEEDED
    assert b._to_status("REPORTED") == OrderStatus.REPORTED


def test_to_status_unknown_string_returns_unknown():
    port = _make_broker_port()
    b = PortBackedBroker(port, "p", BrokerKind.SIMULATION)
    assert b._to_status("bogus-status") == OrderStatus.UNKNOWN


def test_to_order_converts_view():
    """_to_order uses _to_side and _to_status correctly."""
    port = _make_broker_port()
    b = PortBackedBroker(port, "p1", BrokerKind.SIMULATION)
    view = _make_order_view(asset="000002.SZ", side="buy", status="FILLED", qtoid="qt-2")
    order = b._to_order(view)
    assert order.portfolio_id == "p1"
    assert order.asset == "000002.SZ"
    assert order.side == OrderSide.BUY
    assert order.status == OrderStatus.SUCCEEDED
    assert order.bid_type == BidType.UNKNOWN
    assert order.qtoid == "qt-2"
