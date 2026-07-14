"""B08-gateway-broker-2: Tests for GatewayBrokerAdapter helpers.

Push gateway_broker.py from 75.5% toward 80%.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantide.core.enums import OrderSide
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
    GatewayTradeStateConsistencyError,
)
from quantide.core.enums import BrokerKind, OrderSide
import datetime
from quantide.core.runtime.gateway_client import GatewayClient


@pytest.fixture
def adapter():
    client = MagicMock(spec=GatewayClient)
    return GatewayBrokerAdapter(client=client)


@pytest.fixture
def wrapper():
    return GatewayBrokerWrapper(adapter=MagicMock(), portfolio_id="gw-1")


# ---------------------------------------------------------------------------
# Init / properties (Wrapper)
# ---------------------------------------------------------------------------


def test_init_sets_default_attributes(wrapper):
    assert wrapper._portfolio_id == "gw-1"
    assert wrapper._clock is None
    assert wrapper._strategy_cheat_on_close is True
    assert wrapper._live_execution_window == "auction"
    assert wrapper._live_execution_slippage == 0.001
    assert wrapper._deferred_orders == []


def test_set_clock(wrapper):
    dt = datetime.datetime(2024, 1, 1, 10, 0, 0)
    wrapper.set_clock(dt)
    assert wrapper._clock == dt


def test_set_clock_to_none(wrapper):
    wrapper._clock = datetime.datetime.now()
    wrapper.set_clock(None)
    assert wrapper._clock is None


def test_set_strategy_runtime_config(wrapper):
    wrapper.set_strategy_runtime_config(
        cheat_on_close=False,
        live_execution_window="morning",
        live_execution_slippage=0.002,
    )
    assert wrapper._strategy_cheat_on_close is False
    assert wrapper._live_execution_window == "morning"
    assert wrapper._live_execution_slippage == 0.002


def test_set_strategy_runtime_config_defaults(wrapper):
    wrapper.set_strategy_runtime_config()
    assert wrapper._strategy_cheat_on_close is False


# ---------------------------------------------------------------------------
# _read_text (adapter)
# ---------------------------------------------------------------------------


def test_read_text_returns_first_non_empty_string(adapter):
    assert adapter._read_text({"a": "", "b": "hello"}, "a", "b") == "hello"


def test_read_text_returns_when_value_is_non_string(adapter):
    assert adapter._read_text({"a": 5}, "a") == "5"


def test_read_text_returns_none_when_all_empty(adapter):
    assert adapter._read_text({}, "a", "b") is None


def test_read_text_returns_none_when_all_whitespace(adapter):
    assert adapter._read_text({"a": "   "}, "a") is None


def test_read_text_skips_none_values(adapter):
    assert adapter._read_text({"a": None, "b": "x"}, "a", "b") == "x"


# ---------------------------------------------------------------------------
# _parse_time_text (adapter)
# ---------------------------------------------------------------------------


def test_parse_time_text_empty_returns_now(adapter):
    before = datetime.datetime.now()
    got = adapter._parse_time_text("")
    after = datetime.datetime.now()
    assert before <= got <= after


def test_parse_time_text_full_iso(adapter):
    got = adapter._parse_time_text("2024-06-15 10:30:45")
    assert got == datetime.datetime(2024, 6, 15, 10, 30, 45)


def test_parse_time_text_time_only_uses_today(adapter):
    got = adapter._parse_time_text("10:30:45")
    assert got.time() == datetime.time(10, 30, 45)
    assert got.date() == datetime.date.today()


def test_parse_time_text_garbage_falls_back(adapter):
    """Unparseable text returns now()."""
    before = datetime.datetime.now()
    got = adapter._parse_time_text("not-a-time")
    after = datetime.datetime.now()
    assert before <= got <= after


# ---------------------------------------------------------------------------
# _side_matches (adapter)
# ---------------------------------------------------------------------------


def test_side_matches_buy(adapter):
    assert adapter._side_matches("buy", OrderSide.BUY) is True
    assert adapter._side_matches("BUY", OrderSide.BUY) is True
    assert adapter._side_matches("买入", OrderSide.BUY) is True
    assert adapter._side_matches("1", OrderSide.BUY) is True


def test_side_matches_sell(adapter):
    assert adapter._side_matches("sell", OrderSide.SELL) is True
    assert adapter._side_matches("SELL", OrderSide.SELL) is True
    assert adapter._side_matches("卖出", OrderSide.SELL) is True
    assert adapter._side_matches("-1", OrderSide.SELL) is True


def test_side_matches_negative(adapter):
    assert adapter._side_matches("sell", OrderSide.BUY) is False
    assert adapter._side_matches("buy", OrderSide.SELL) is False


def test_side_matches_unknown(adapter):
    assert adapter._side_matches("xxx", OrderSide.UNKNOWN) is False


# ---------------------------------------------------------------------------
# GatewayTradeStateConsistencyError
# ---------------------------------------------------------------------------


def test_consistency_error_is_runtime_error():
    err = GatewayTradeStateConsistencyError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"


# ---------------------------------------------------------------------------
# _remember_order_mapping (adapter)
# ---------------------------------------------------------------------------


def test_remember_mapping_no_external_no_op(adapter):
    adapter._remember_order_mapping(qtoid="q1", external_order_id=None)
    assert adapter._qtoid_to_external_order_id == {}
    assert adapter._external_order_id_to_qtoid == {}


def test_remember_mapping_same_id_no_op(adapter):
    adapter._remember_order_mapping(qtoid="q1", external_order_id="q1")
    assert adapter._qtoid_to_external_order_id == {}


def test_remember_mapping_records_both_directions(adapter):
    adapter._remember_order_mapping(qtoid="q1", external_order_id="e1")
    assert adapter._qtoid_to_external_order_id == {"q1": "e1"}
    assert adapter._external_order_id_to_qtoid == {"e1": "q1"}


def test_remember_mapping_raises_on_conflict(adapter):
    """If external_order_id already maps to a different qtoid, raises."""
    adapter._external_order_id_to_qtoid["e1"] = "q1"
    with pytest.raises(GatewayTradeStateConsistencyError):
        adapter._remember_order_mapping(qtoid="q2", external_order_id="e1")


def test_remember_mapping_raises_on_reverse_conflict(adapter):
    """If qtoid already maps to a different external_order_id, raises."""
    adapter._qtoid_to_external_order_id["q1"] = "e1"
    with pytest.raises(GatewayTradeStateConsistencyError):
        adapter._remember_order_mapping(qtoid="q1", external_order_id="e2")


def test_remember_mapping_idempotent(adapter):
    adapter._remember_order_mapping(qtoid="q1", external_order_id="e1")
    # Second call with same mapping should not raise.
    adapter._remember_order_mapping(qtoid="q1", external_order_id="e1")
    assert adapter._qtoid_to_external_order_id == {"q1": "e1"}


# ---------------------------------------------------------------------------
# _resolve_qtoid (adapter)
# ---------------------------------------------------------------------------


def test_resolve_qtoid_with_both_returns_qtoid(adapter):
    got = adapter._resolve_qtoid({"qtoid": "q1", "order_id": "e1"}, context="submit")
    assert got == "q1"
    assert adapter._qtoid_to_external_order_id == {"q1": "e1"}


def test_resolve_qtoid_only_qtoid_no_request(adapter):
    got = adapter._resolve_qtoid({"qtoid": "q1"}, context="submit")
    assert got == "q1"


def test_resolve_qtoid_qtoid_matches_request(adapter):
    got = adapter._resolve_qtoid({"qtoid": "q1"}, context="submit", requested_qtoid="q1")
    assert got == "q1"


def test_resolve_qtoid_qtoid_mismatch_request_raises(adapter):
    with pytest.raises(GatewayTradeStateConsistencyError):
        adapter._resolve_qtoid({"qtoid": "q1"}, context="submit", requested_qtoid="q2")


def test_resolve_qtoid_external_mapped(adapter):
    adapter._external_order_id_to_qtoid["e1"] = "q1"
    got = adapter._resolve_qtoid({"order_id": "e1"}, context="query")
    assert got == "q1"


def test_resolve_qtoid_external_with_request_no_qtoid(adapter):
    """external_order_id + requested_qtoid: maps requested → external."""
    got = adapter._resolve_qtoid({"order_id": "e1"}, context="submit", requested_qtoid="qx")
    assert got == "qx"
    assert adapter._qtoid_to_external_order_id == {"qx": "e1"}


def test_resolve_qtoid_requested_only(adapter):
    got = adapter._resolve_qtoid({}, context="submit", requested_qtoid="qx")
    assert got == "qx"


def test_resolve_qtoid_no_qtoid_no_external_raises(adapter):
    with pytest.raises(GatewayTradeStateConsistencyError):
        adapter._resolve_qtoid({}, context="submit")


# ---------------------------------------------------------------------------
# GatewayBrokerWrapper basic buy/sell flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrapper_buy_when_cheat_on_close_submits_immediately():
    """When cheat_on_close=True (default), buy calls adapter.submit."""
    client = MagicMock()
    adapter = GatewayBrokerAdapter(client=client)
    wrapper = GatewayBrokerWrapper(adapter=adapter, portfolio_id="p1")
    wrapper.set_strategy_runtime_config(cheat_on_close=True)
    fake_ack = MagicMock()
    fake_ack.order_id = "q1"
    fake_ack.exec_id = "e1"
    fake_ack.asset = "000001.SZ"
    fake_ack.shares = 100.0
    fake_ack.price = 10.0
    fake_ack.amount = 1000.0
    fake_ack.ack_time = None
    adapter.submit = AsyncMock(return_value=fake_ack)
    out = await wrapper.buy(asset="000001.SZ", shares=100)
    assert out is not None


@pytest.mark.asyncio
async def test_wrapper_buy_when_not_cheat_appends_to_deferred():
    """When cheat_on_close=False, adds to deferred_orders."""
    client = MagicMock()
    adapter = GatewayBrokerAdapter(client=client)
    wrapper = GatewayBrokerWrapper(adapter=adapter, portfolio_id="p1")
    wrapper.set_strategy_runtime_config(cheat_on_close=False)
    out = await wrapper.buy(asset="000001.SZ", shares=100)
    assert len(wrapper.deferred_orders) == 1
    assert wrapper.deferred_orders[0]["asset"] == "000001.SZ"
    assert wrapper.deferred_orders[0]["side"] == OrderSide.BUY


@pytest.mark.asyncio
async def test_wrapper_sell_when_not_cheat_appends_to_deferred():
    client = MagicMock()
    adapter = GatewayBrokerAdapter(client=client)
    wrapper = GatewayBrokerWrapper(adapter=adapter, portfolio_id="p1")
    wrapper.set_strategy_runtime_config(cheat_on_close=False)
    out = await wrapper.sell(asset="000001.SZ", shares=100)
    assert len(wrapper.deferred_orders) == 1
    assert wrapper.deferred_orders[0]["side"] == OrderSide.SELL


@pytest.mark.asyncio
async def test_wrapper_cancel_order():
    client = MagicMock()
    adapter = GatewayBrokerAdapter(client=client)
    adapter.cancel = AsyncMock(return_value=None)
    wrapper = GatewayBrokerWrapper(adapter=adapter, portfolio_id="p1")
    await wrapper.cancel_order(qt_oid="q1")
    adapter.cancel.assert_awaited_once_with("q1")


@pytest.mark.asyncio
async def test_wrapper_buy_amount_and_percent():
    """buy_amount + buy_percent behave similarly."""
    client = MagicMock()
    adapter = GatewayBrokerAdapter(client=client)
    wrapper = GatewayBrokerWrapper(adapter=adapter, portfolio_id="p1")
    wrapper.set_strategy_runtime_config(cheat_on_close=False)
    await wrapper.buy_amount(asset="000001.SZ", amount=1000)
    await wrapper.buy_percent(asset="000001.SZ", percent=0.1)
    assert len(wrapper.deferred_orders) == 2


@pytest.mark.asyncio
async def test_wrapper_sell_amount_and_percent():
    client = MagicMock()
    adapter = GatewayBrokerAdapter(client=client)
    wrapper = GatewayBrokerWrapper(adapter=adapter, portfolio_id="p1")
    wrapper.set_strategy_runtime_config(cheat_on_close=False)
    await wrapper.sell_amount(asset="000001.SZ", amount=1000)
    await wrapper.sell_percent(asset="000001.SZ", percent=0.1)
    assert len(wrapper.deferred_orders) == 2


def test_wrapper_clock_set_and_get():
    wrapper = GatewayBrokerWrapper(adapter=MagicMock(), portfolio_id="p1")
    assert wrapper._clock is None
    wrapper.set_clock(__import__("datetime").datetime.now())
    assert wrapper._clock is not None


def test_wrapper_kinds():
    wrapper = GatewayBrokerWrapper(adapter=MagicMock(), portfolio_id="p1")
    assert wrapper.kind == BrokerKind.QMT


def test_wrapper_strategy_runtime_config():
    wrapper = GatewayBrokerWrapper(adapter=MagicMock(), portfolio_id="p1")
    wrapper.set_strategy_runtime_config(
        cheat_on_close=True,
        live_execution_window="morning",
        live_execution_slippage=0.005,
    )
    assert wrapper._strategy_cheat_on_close is True
    assert wrapper._live_execution_window == "morning"
    assert wrapper._live_execution_slippage == 0.005
