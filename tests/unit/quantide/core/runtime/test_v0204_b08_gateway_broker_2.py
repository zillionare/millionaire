"""B08-gateway-broker-2: Tests for GatewayBrokerAdapter helpers.

Push gateway_broker.py from 75.5% toward 80%.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from quantide.core.enums import OrderSide
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
    GatewayTradeStateConsistencyError,
)
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
