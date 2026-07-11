"""FR-0301 AC-1..AC-4: Tushare boundary and registry contracts."""

import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from quantide.data.fetchers.registry import DataFetcherRegistry
from quantide.data.fetchers.tushare import (
    fetch_bars,
    fetch_bars_ext,
    fetch_calendar,
)


def test_calendar_calls_tushare_at_sdk_boundary(monkeypatch):
    """FR-0301 AC-1: calendar forwards the epoch without a network request."""
    calls = []

    def trade_cal(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame(
                {"cal_date": ["20240102"], "pretrade_date": ["20240101"], "is_open": [1]}
            )

    monkeypatch.setattr("tushare.pro_api", lambda: SimpleNamespace(trade_cal=trade_cal))

    result = fetch_calendar(dt.date(2024, 1, 2))

    assert calls == [{"exchange": "SSE", "start_date": "20240102"}]
    assert result.index.tolist() == [dt.date(2024, 1, 2)]
    assert result.loc[dt.date(2024, 1, 2), "is_open"] == 1


def test_bars_collects_a_failed_batch_and_keeps_successful_data(monkeypatch):
    """FR-0301 AC-3: a failed date is reported while later dates remain usable."""
    def daily(*, trade_date, **_kwargs):
        if trade_date == "20240102":
            raise RuntimeError("transient SDK failure")
        return pd.DataFrame(
            {"trade_date": [trade_date], "ts_code": ["000001.SZ"], "open": [10], "high": [11], "low": [9], "close": [10.5], "vol": [100], "amount": [1000]}
        )

    monkeypatch.setattr("tushare.pro_api", lambda: SimpleNamespace(daily=daily))

    frame, errors = fetch_bars([dt.date(2024, 1, 2), dt.date(2024, 1, 3)])

    assert frame["asset"].tolist() == ["000001.SZ"]
    assert frame["date"].dt.date.tolist() == [dt.date(2024, 1, 3)]
    assert errors[0][0:2] == ["daily", dt.date(2024, 1, 2)]


def test_bars_ext_join_keeps_all_consumable_market_columns(monkeypatch):
    """FR-0301 AC-2: joined bars expose OHLCV, limits, adjustment and ST fields."""
    def response_for(name):
        def method(*, trade_date, **_kwargs):
            common = {"trade_date": [trade_date], "ts_code": ["000001.SZ"]}
            if name == "daily":
                return pd.DataFrame({**common, "open": [10], "high": [11], "low": [9], "close": [10.5], "vol": [100], "amount": [1000]})
            if name == "adj_factor":
                return pd.DataFrame({**common, "adj_factor": [1.2]})
            if name == "stk_limit":
                return pd.DataFrame({**common, "up_limit": [11.55], "down_limit": [9.45]})
            return pd.DataFrame({**common, "name": ["ST test"]})

        return method

    pro = SimpleNamespace(**{name: response_for(name) for name in ("daily", "adj_factor", "stk_limit", "stock_st")})
    monkeypatch.setattr("tushare.pro_api", lambda: pro)

    frame, errors = fetch_bars_ext(dt.date(2024, 1, 3))

    assert errors == []
    assert {"asset", "date", "open", "high", "low", "close", "volume", "amount", "adjust", "is_st", "up_limit", "down_limit"} <= set(frame.columns)
    assert frame.iloc[0][["adjust", "is_st", "up_limit", "down_limit"]].tolist() == [1.2, True, 11.55, 9.45]


def test_registry_exposes_default_unknown_and_replacement_behavior():
    """FR-0301 AC-4: registry exposes its default and replacement semantics."""
    registry = DataFetcherRegistry()
    first, replacement = object(), object()

    registry.register("first", first, make_default=True)
    registry.register("first", replacement)

    assert registry.has("first")
    assert registry.list_names() == ["first"]
    assert registry.get() is replacement
    with pytest.raises(KeyError, match="not found"):
        registry.get("missing")
