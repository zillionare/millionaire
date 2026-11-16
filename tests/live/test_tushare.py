"""Small, read-only source probes; never run in the routine offline suite."""

from __future__ import annotations

import os

import pytest
import tushare as ts

pytestmark = pytest.mark.live_data


@pytest.fixture(scope="module")
def client():
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        message = "LIVE_SKIPPED: missing TUSHARE_TOKEN"
        if os.environ.get("QUANTIDE_REQUIRE_LIVE_DATA") == "1":
            pytest.fail(message)
        pytest.skip(message)
    # Direct injection avoids writing SDK token files. Assertion and JUnit
    # output never contain the client or credential.
    return ts.pro_api(token=token, timeout=6)


def test_calendar_source(client):
    frame = client.trade_cal(
        exchange="SSE",
        start_date="20240102",
        end_date="20240103",
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    assert set(frame["cal_date"]) == {"20240102", "20240103"}
    assert set(frame["is_open"]) == {1}


def test_daily_price_source(client):
    frame = client.daily(
        ts_code="000001.SZ",
        start_date="20240102",
        end_date="20240103",
        fields="ts_code,trade_date,open,high,low,close,vol,amount",
    )
    assert len(frame) == 2
    assert set(frame["trade_date"]) == {"20240102", "20240103"}
    assert set(frame["ts_code"]) == {"000001.SZ"}
    assert (frame["low"] <= frame["close"]).all()
    assert (frame["close"] <= frame["high"]).all()
    assert (frame[["open", "high", "low", "close", "vol", "amount"]] > 0).all().all()
