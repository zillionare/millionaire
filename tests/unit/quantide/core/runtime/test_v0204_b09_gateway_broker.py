"""B09-gateway-broker-2: Tests for quantide/core/runtime/gateway_broker.py helpers.

Target: 4 tests covering simple helpers/properties currently at 75.3%.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from quantide.core.runtime.gateway_broker import (
    GatewayBrokerWrapper,
)


def _make_wrapper() -> GatewayBrokerWrapper:
    """Build a GatewayBrokerWrapper with a dummy adapter (no calls needed for helpers)."""
    return GatewayBrokerWrapper(object())  # type: ignore[arg-type]


def test_empty_history_frame_schema():
    """_empty_history_frame returns an empty polars DataFrame with the expected date/asset columns."""
    df = _make_wrapper()._empty_history_frame()
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()
    for col in ("date", "asset", "open", "high", "low", "close", "volume", "adjust"):
        assert col in df.columns


def test_set_clock_and_strategy_runtime_config_store_values():
    """set_clock and set_strategy_runtime_config persist their parameters on the wrapper."""
    wrapper = _make_wrapper()
    now = dt.datetime(2024, 1, 1, 10, 0)
    wrapper.set_clock(now)
    assert wrapper._clock == now

    wrapper.set_strategy_runtime_config(
        cheat_on_close=True,
        live_execution_window="intraday",
        live_execution_slippage=0.005,
    )
    assert wrapper._strategy_cheat_on_close is True
    assert wrapper._live_execution_window == "intraday"
    assert wrapper._live_execution_slippage == 0.005


def test_deferred_orders_returns_copy_list():
    """deferred_orders returns a list (copy) of the internal deferred orders buffer."""
    wrapper = _make_wrapper()
    out = wrapper.deferred_orders
    assert isinstance(out, list)
    assert out == []
    # Mutating the returned list must not affect internal state.
    out.append({"x": 1})
    assert wrapper.deferred_orders == []


def test_previous_trade_date_falls_back_on_calendar_error(monkeypatch):
    """_previous_trade_date returns today-1day when calendar.day_shift raises."""
    wrapper = _make_wrapper()
    today = dt.date(2024, 5, 10)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("calendar not loaded")

    # calendar is imported as module-level name in gateway_broker; patch the bound method.
    from quantide.data.models.calendar import calendar as cal_module_obj

    monkeypatch.setattr(cal_module_obj, "day_shift", _raise)

    result = wrapper._previous_trade_date(today)
    assert result == today - dt.timedelta(days=1)
