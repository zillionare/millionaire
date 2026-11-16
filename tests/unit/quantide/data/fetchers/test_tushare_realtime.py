"""Minute-frequency snapshots must preserve source time, units and trading constraints."""

import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from quantide.data.fetchers.tushare_realtime import TushareRealtimeFetcher, normalized_snapshot

NOW = datetime.datetime(2024, 1, 3, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def quote(**updates):
    return {"ts_code": "000001.SZ", "open": 10.0, "high": 10.5, "low": 9.8,
            "close": 10.2, "pre_close": 10.0, "vol": 10000, "amount": 100000,
            "trade_time": "2024-01-03 10:00:00", **updates}


def test_snapshot_converts_shares_yuan_and_preserves_reference_timestamp():
    row = normalized_snapshot(quote(), {"up_limit": 11, "down_limit": 9}, NOW)
    assert row["volume"] == 100
    assert row["amount"] == 100
    assert row["price"] == 10.2
    assert row["prev_close"] == 10
    assert row["ts"] == NOW


@pytest.mark.parametrize("stamp", [None, "10:00:00", "2024-01-02 10:00:00",
                                   "2024-01-03 09:55:00", "2024-01-03 11:00:00"])
def test_stale_missing_or_undated_time_is_not_replaced_with_now(stamp):
    assert normalized_snapshot(quote(trade_time=stamp), {"up_limit": 11, "down_limit": 9}, NOW) is None


@pytest.mark.parametrize("limits", [{}, {"up_limit": 11}, {"up_limit": 0, "down_limit": 9},
                                    {"up_limit": 9, "down_limit": 11}])
def test_missing_or_invalid_price_limits_fail_closed(limits):
    assert normalized_snapshot(quote(), limits, NOW) is None


@pytest.mark.parametrize("updates", [{"close": float("nan")}, {"vol": -1},
                                     {"amount": float("inf")}, {"pre_close": 0}])
def test_invalid_price_reference_or_volume_is_rejected(updates):
    assert normalized_snapshot(quote(**updates), {"up_limit": 11, "down_limit": 9}, NOW) is None


def test_same_day_limits_are_cached_but_never_reused_across_days():
    calls = []

    def limits(**params):
        calls.append(params)
        return pd.DataFrame([{"ts_code": "000001.SZ", "up_limit": 11, "down_limit": 9,
                              "trade_date": params["trade_date"]}])

    client = SimpleNamespace(stk_limit=limits, rt_k=lambda **params: pd.DataFrame([quote()]))
    fetcher = TushareRealtimeFetcher(client)
    assert fetcher.fetch_quote_snapshot(["000001.SZ"], NOW)
    assert fetcher.fetch_quote_snapshot(["000001.SZ"], NOW)
    assert len(calls) == 1
    fetcher.fetch_quote_snapshot(["000001.SZ"], NOW + datetime.timedelta(days=1))
    assert len(calls) == 2
    assert calls[-1]["trade_date"] == "20240104"


def test_previous_days_limit_response_is_not_cached_or_published():
    client = SimpleNamespace(
        stk_limit=lambda **kw: pd.DataFrame([{"ts_code": "000001.SZ", "up_limit": 11,
                                             "down_limit": 9, "trade_date": "20240102"}]),
        rt_k=lambda **kw: pytest.fail("must not request without same-day limits"),
    )
    fetcher = TushareRealtimeFetcher(client)
    assert fetcher.fetch_quote_snapshot(["000001.SZ"], NOW) == {}
    assert fetcher._day is None
