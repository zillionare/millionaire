"""B08-gateway-broker-1: Tests for quantide/core/runtime/gateway_broker.py helpers.

Target: gateway_broker.py is one of the most-imported core modules
(10 imports), currently 75.3% coverage. Cover the simple helper
functions to push toward 80%.
"""

from __future__ import annotations

import pytest

from quantide.core.enums import OrderSide, OrderStatus
from quantide.core.runtime.gateway_broker import (
    GatewayTradeStateConsistencyError,
    _coerce_order_side,
    _coerce_order_status,
)


# ---------------------------------------------------------------------------
# GatewayTradeStateConsistencyError
# ---------------------------------------------------------------------------


def test_consistency_error_is_runtime_error():
    err = GatewayTradeStateConsistencyError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"


# ---------------------------------------------------------------------------
# _coerce_order_side
# ---------------------------------------------------------------------------


def test_coerce_order_side_lowercase_buy():
    assert _coerce_order_side("buy") == OrderSide.BUY


def test_coerce_order_side_lowercase_sell():
    assert _coerce_order_side("sell") == OrderSide.SELL


def test_coerce_order_side_uppercase_buy():
    assert _coerce_order_side("BUY") == OrderSide.BUY


def test_coerce_order_side_uppercase_sell():
    assert _coerce_order_side("SELL") == OrderSide.SELL


def test_coerce_order_side_letter_b():
    assert _coerce_order_side("b") == OrderSide.BUY


def test_coerce_order_side_letter_s():
    assert _coerce_order_side("s") == OrderSide.SELL


def test_coerce_order_side_digit_1():
    assert _coerce_order_side("1") == OrderSide.BUY


def test_coerce_order_side_digit_negative_1():
    assert _coerce_order_side("-1") == OrderSide.SELL


def test_coerce_order_side_unknown_returns_unknown():
    assert _coerce_order_side("") == OrderSide.UNKNOWN
    assert _coerce_order_side(None) == OrderSide.UNKNOWN
    assert _coerce_order_side("xxx") == OrderSide.UNKNOWN


def test_coerce_order_side_handles_whitespace():
    assert _coerce_order_side("  buy  ") == OrderSide.BUY


# ---------------------------------------------------------------------------
# _coerce_order_status
# ---------------------------------------------------------------------------


def test_coerce_order_status_unreported():
    assert _coerce_order_status("unreported") == OrderStatus.UNREPORTED


def test_coerce_order_status_pending():
    assert _coerce_order_status("pending") == OrderStatus.WAIT_REPORTING


def test_coerce_order_status_reported():
    assert _coerce_order_status("reported") == OrderStatus.REPORTED


def test_coerce_order_status_canceling():
    assert _coerce_order_status("canceling") == OrderStatus.REPORTED_CANCEL


def test_coerce_order_status_partial_canceling():
    assert _coerce_order_status("partial_canceling") == OrderStatus.PARTSUCC_CANCEL


def test_coerce_order_status_partial_cancelled():
    assert _coerce_order_status("partial_cancelled") == OrderStatus.PART_CANCEL


def test_coerce_order_status_cancelled():
    assert _coerce_order_status("cancelled") == OrderStatus.CANCELED


def test_coerce_order_status_canceled_us_spelling():
    assert _coerce_order_status("canceled") == OrderStatus.CANCELED


def test_coerce_order_status_partial():
    assert _coerce_order_status("partial") == OrderStatus.PART_SUCC


def test_coerce_order_status_filled():
    assert _coerce_order_status("filled") == OrderStatus.SUCCEEDED


def test_coerce_order_status_rejected():
    assert _coerce_order_status("rejected") == OrderStatus.JUNK


def test_coerce_order_status_unknown_returns_unknown():
    assert _coerce_order_status("weird-status") == OrderStatus.UNKNOWN
    assert _coerce_order_status("") == OrderStatus.UNKNOWN
    assert _coerce_order_status(None) == OrderStatus.UNKNOWN


def test_coerce_order_status_handles_uppercase():
    """Strings are lowercased before mapping."""
    assert _coerce_order_status("FILLED") == OrderStatus.SUCCEEDED


def test_coerce_order_status_handles_whitespace():
    assert _coerce_order_status("  filled  ") == OrderStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# GatewayBrokerWrapper — setters
# ---------------------------------------------------------------------------


def test_wrapper_set_clock_stores_dt():
    """set_clock stores the given datetime in _clock."""
    from quantide.core.runtime.gateway_broker import GatewayBrokerWrapper

    fake_adapter = object()  # wrapper holds a reference; type not used by setter.
    wrapper = GatewayBrokerWrapper(fake_adapter)  # type: ignore[arg-type]
    wrapper.set_clock(None)
    assert wrapper._clock is None
    import datetime
    now = datetime.datetime(2024, 1, 1, 10, 0)
    wrapper.set_clock(now)
    assert wrapper._clock == now


def test_wrapper_set_strategy_runtime_config_coerces_types():
    """set_strategy_runtime_config coerces parameter types to expected types."""
    from quantide.core.runtime.gateway_broker import GatewayBrokerWrapper

    fake_adapter = object()
    wrapper = GatewayBrokerWrapper(fake_adapter)  # type: ignore[arg-type]
    wrapper.set_strategy_runtime_config(
        cheat_on_close=1,  # truthy → True
        live_execution_window="intraday",
        live_execution_slippage="0.005",  # string "0.005" → 0.005
    )
    assert wrapper._strategy_cheat_on_close is True
    assert wrapper._live_execution_window == "intraday"
    assert wrapper._live_execution_slippage == 0.005
    assert isinstance(wrapper._live_execution_slippage, float)


def test_wrapper_set_strategy_runtime_config_falsy_cheat():
    """cheat_on_close=False is preserved (not coerced to True by truthy)."""
    from quantide.core.runtime.gateway_broker import GatewayBrokerWrapper

    fake_adapter = object()
    wrapper = GatewayBrokerWrapper(fake_adapter)  # type: ignore[arg-type]
    wrapper.set_strategy_runtime_config(cheat_on_close=False)
    assert wrapper._strategy_cheat_on_close is False


def test_wrapper_empty_history_frame_returns_empty_df():
    """_empty_history_frame returns an empty pl.DataFrame with expected schema."""
    import polars as pl
    from quantide.core.runtime.gateway_broker import GatewayBrokerWrapper

    fake_adapter = object()
    wrapper = GatewayBrokerWrapper(fake_adapter)  # type: ignore[arg-type]
    df = wrapper._empty_history_frame()
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()
    # Schema should have expected columns.
    cols = df.columns
    for col in ("date", "asset", "open", "high", "low", "close", "volume"):
        assert col in cols, f"missing column {col}"
