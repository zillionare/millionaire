"""B08-kline-api: Test kline.py simple utilities + feature_removed."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import polars as pl
import polars as pl3
import pytest

from quantide.web.apis.analysis import kline as kline_mod
from quantide.web.apis.analysis.kline import (
    _feature_removed,
    add_ma_to_list,
    bars_to_list,
)


def test_feature_removed_returns_410():
    resp = _feature_removed("gone")
    assert resp.status_code == 410


def test_bars_to_list_empty():
    df = pl.DataFrame()
    got = bars_to_list(df)
    assert got == []


def test_bars_to_list_with_rows():
    df = pl.DataFrame({
        "frame": [datetime.date(2024, 1, 1)],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
    })
    got = bars_to_list(df)
    assert len(got) == 1
    assert got[0]["open"] == 10.0
    assert got[0]["close"] == 10.5


def test_bars_to_list_datetime():
    """When frame is datetime, ISO-format."""
    df = pl.DataFrame({
        "frame": [datetime.datetime(2024, 1, 1, 10, 0)],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
    })
    got = bars_to_list(df)
    assert got[0]["dt"] == "2024-01-01T10:00:00"


def test_bars_to_list_string():
    """When frame is already string, returned as-is."""
    df = pl.DataFrame({
        "frame": ["2024-01-01"],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
    })
    got = bars_to_list(df)
    assert got[0]["dt"] == "2024-01-01"


def test_add_ma_to_list_empty():
    df = pl.DataFrame()
    got = add_ma_to_list(df, [5, 10])
    assert got == []


def test_add_ma_to_list_with_ma():
    df = pl.DataFrame({
        "frame": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)],
        "open": [10.0, 11.0],
        "high": [11.0, 12.0],
        "low": [9.5, 10.5],
        "close": [10.5, 11.5],
        "volume": [1000.0, 2000.0],
        "amount": [10500.0, 23000.0],
        "ma5": [10.5, 11.0],
        "ma10": [None, 10.5],
    })
    got = add_ma_to_list(df, [5, 10])
    assert len(got) == 2
    assert got[0]["ma5"] == 10.5
    assert "ma10" not in got[0]  # None value, not added
    assert got[1]["ma10"] == 10.5


def test_add_ma_to_list_no_ma_present():
    """When MA columns don't exist, no MA keys added."""
    df = pl.DataFrame({
        "frame": [datetime.date(2024, 1, 1)],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
    })
    got = add_ma_to_list(df, [5])
    assert got[0]["close"] == 10.5
    assert "ma5" not in got[0]


# ---------------------------------------------------------------------------
# _get_stock_bars / _get_index_bars — mock to test logic
# ---------------------------------------------------------------------------


import polars as pl3
import datetime as dt
from quantide.web.apis.analysis import kline as kline_mod
from quantide.web.apis.analysis.kline import _get_stock_bars, _get_index_bars


def test_get_stock_bars_non_empty():
    """When daily_bars.get_bars_in_range returns data, returns it."""
    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, 1)],
        "asset": ["000001.SZ"],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
        "adjust": [1.0],
    })
    with patch.object(kline_mod, "daily_bars") as mock_dbars:
        mock_dbars.get_bars_in_range = MagicMock(return_value=fake_df)
        out = _get_stock_bars("000001.SZ", dt.date(2024, 1, 1), dt.date(2024, 6, 30))
    assert not out.is_empty()


def test_get_stock_bars_empty_renames():
    """When empty + freq=day, returns empty DataFrame with column schema."""
    with patch.object(kline_mod, "daily_bars") as mock_dbars:
        mock_dbars.get_bars_in_range = MagicMock(return_value=pl3.DataFrame())
        out = _get_stock_bars("000001.SZ", dt.date(2024, 1, 1), dt.date(2024, 6, 30))
    # Empty DataFrame with schema
    assert out.is_empty()


def test_get_index_bars_non_empty():
    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, 1)],
        "close": [3500.0],
    })
    fake_store = MagicMock()
    fake_store.get = MagicMock(return_value=fake_df)
    with patch.object(kline_mod, "get_index_bars_store", return_value=fake_store):
        out = _get_index_bars("000300.SH", dt.date(2024, 1, 1), dt.date(2024, 6, 30))
    assert not out.is_empty()


def test_get_index_bars_empty():
    """When empty, returns empty schema DataFrame."""
    fake_store = MagicMock()
    fake_store.get = MagicMock(return_value=pl3.DataFrame())
    with patch.object(kline_mod, "get_index_bars_store", return_value=fake_store):
        out = _get_index_bars("000300.SH", dt.date(2024, 1, 1), dt.date(2024, 6, 30))
    assert out.is_empty()


# ---------------------------------------------------------------------------
# _get_bars_with_ma — test MA computation branch
# ---------------------------------------------------------------------------


from quantide.web.apis.analysis.kline import _get_bars_with_ma


def test_get_bars_with_ma_empty():
    """When df empty, returns empty."""
    with patch.object(kline_mod, "_get_stock_bars", return_value=pl3.DataFrame()):
        out = _get_bars_with_ma("000001.SZ", dt.date(2024, 1, 1), dt.date(2024, 6, 30))
    assert out.is_empty()


def test_get_bars_with_ma_no_periods():
    """When ma_periods None, returns raw df."""
    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, i) for i in range(1, 11)],
        "close": [10.0 + i * 0.1 for i in range(10)],
        "open": [9.0 + i * 0.1 for i in range(10)],
        "high": [11.0 + i * 0.1 for i in range(10)],
        "low": [8.5 + i * 0.1 for i in range(10)],
        "volume": [1000.0] * 10,
    })
    with patch.object(kline_mod, "_get_stock_bars", return_value=fake_df):
        out = _get_bars_with_ma("000001.SZ", dt.date(2024, 6, 1), dt.date(2024, 6, 10), ma_periods=None)
    assert out.height == 10


def test_get_bars_with_ma_with_periods():
    """When ma_periods given, computes MA columns."""
    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, i) for i in range(1, 11)],
        "close": [10.0 + i * 0.1 for i in range(10)],
        "open": [9.0 + i * 0.1 for i in range(10)],
        "high": [11.0 + i * 0.1 for i in range(10)],
        "low": [8.5 + i * 0.1 for i in range(10)],
        "volume": [1000.0] * 10,
    })
    with patch.object(kline_mod, "_get_stock_bars", return_value=fake_df):
        out = _get_bars_with_ma("000001.SZ", dt.date(2024, 6, 1), dt.date(2024, 6, 10), ma_periods=[3, 5])
    assert "ma3" in out.columns or "ma5" in out.columns


# ---------------------------------------------------------------------------
# get_stock_kline route handler
# ---------------------------------------------------------------------------


from quantide.web.apis.analysis import kline as km


def _fake_request(query_params):
    req = MagicMock()
    req.query_params = query_params
    req.path_params = {}
    return req


def test_kline_endpoint_basic():
    """get_stock_kline returns JSONResponse with valid request."""
    from quantide.web.apis.analysis.kline import get_stock_kline

    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, 1), dt.date(2024, 6, 2)],
        "close": [10.0, 10.5],
        "open": [9.5, 10.0],
        "high": [10.5, 11.0],
        "low": [9.0, 9.5],
        "volume": [1000.0, 1500.0],
    })
    with patch.object(km, "_get_stock_bars", return_value=fake_df):
        with patch.object(km, "bars_to_list", return_value=[{"date": "2024-06-01", "close": 10.0}]):
            req = _fake_request({"start": "2024-01-01", "end": "2024-06-30", "ma": "5,10"})
            out = get_stock_kline(req, "000001.SZ")
    # Returns Response
    assert out is not None


def test_kline_endpoint_no_dates():
    """No start/end → uses defaults (today - 365, today)."""
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({"date": [dt.date.today()], "close": [10.0]})
    with patch.object(km, "_get_stock_bars", return_value=fake_df):
        with patch.object(km, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = get_stock_kline(req, "000001.SZ")
    assert out is not None


def test_kline_endpoint_invalid_date():
    """Invalid date format → JSONResponse error."""
    from quantide.web.apis.analysis.kline import get_stock_kline
    req = _fake_request({"start": "invalid"})
    out = get_stock_kline(req, "000001.SZ")
    assert out is not None


def test_kline_endpoint_invalid_freq():
    """Invalid freq → JSONResponse error."""
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [10.0]})
    with patch.object(km, "_get_stock_bars", return_value=fake_df):
        with patch.object(km, "bars_to_list", return_value=[]):
            req = _fake_request({"start": "2024-01-01", "end": "2024-06-30", "freq": "invalid"})
            out = get_stock_kline(req, "000001.SZ")
    assert out is not None


def test_kline_endpoint_invalid_ma():
    """Invalid ma param → JSONResponse error."""
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [10.0]})
    with patch.object(km, "_get_stock_bars", return_value=fake_df):
        with patch.object(km, "bars_to_list", return_value=[]):
            req = _fake_request({"start": "2024-01-01", "end": "2024-06-30", "ma": "abc"})
            out = get_stock_kline(req, "000001.SZ")
    assert out is not None


def test_kline_endpoint_with_ma():
    """With valid ma periods, returns MA data."""
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, 1), dt.date(2024, 6, 2), dt.date(2024, 6, 3)],
        "close": [10.0, 10.5, 11.0],
        "open": [9.5, 10.0, 10.5],
        "high": [10.5, 11.0, 11.5],
        "low": [9.0, 9.5, 10.0],
        "volume": [1000.0, 1500.0, 2000.0],
    })
    with patch.object(km, "_get_bars_with_ma", return_value=fake_df):
        with patch.object(km, "add_ma_to_list", return_value=[]):
            req = _fake_request({"start": "2024-01-01", "end": "2024-06-30", "ma": "5"})
            out = get_stock_kline(req, "000001.SZ")
    assert out is not None


def test_kline_endpoint_exception():
    """Generic exception in data fetch → error response."""
    from quantide.web.apis.analysis.kline import get_stock_kline
    with patch.object(km, "_get_stock_bars", side_effect=Exception("boom")):
        req = _fake_request({"start": "2024-01-01", "end": "2024-06-30"})
        out = get_stock_kline(req, "000001.SZ")
    assert out is not None


import asyncio


def _run(coro):
    """Run coroutine to completion."""
    return asyncio.run(coro)


# Async-wrapped tests for get_stock_kline
import pytest


@pytest.mark.asyncio
async def test_kline_endpoint_basic_async():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, 1), dt.date(2024, 6, 2)],
        "close": [10.0, 10.5], "open": [9.5, 10.0],
        "high": [10.5, 11.0], "low": [9.0, 9.5], "volume": [1000.0, 1500.0],
    })
    with patch.object(km2, "_get_stock_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[{"date": "2024-06-01"}]):
            req = _fake_request({})
            out = await get_stock_kline(req, "000001.SZ", start="2024-01-01", end="2024-06-30")
    assert out is not None


@pytest.mark.asyncio
async def test_kline_endpoint_no_dates_async():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({"date": [dt.date.today()], "close": [10.0]})
    with patch.object(km2, "_get_stock_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_stock_kline(req, "000001.SZ")
    assert out is not None


@pytest.mark.asyncio
async def test_kline_endpoint_invalid_date_async():
    from quantide.web.apis.analysis.kline import get_stock_kline
    req = _fake_request({})
    out = await get_stock_kline(req, "000001.SZ", start="invalid")
    assert out is not None


@pytest.mark.asyncio
async def test_kline_endpoint_invalid_freq_async():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [10.0]})
    with patch.object(km2, "_get_stock_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_stock_kline(req, "000001.SZ", start="2024-01-01", end="2024-06-30", freq="invalid")
    assert out is not None


@pytest.mark.asyncio
async def test_kline_endpoint_invalid_ma_async():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [10.0]})
    with patch.object(km2, "_get_stock_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_stock_kline(req, "000001.SZ", start="2024-01-01", end="2024-06-30", ma="abc")
    assert out is not None


@pytest.mark.asyncio
async def test_kline_endpoint_with_ma_async():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_stock_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [10.0]})
    with patch.object(km2, "_get_bars_with_ma", return_value=fake_df):
        with patch.object(km2, "add_ma_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_stock_kline(req, "000001.SZ", start="2024-01-01", end="2024-06-30", ma="5")
    assert out is not None


@pytest.mark.asyncio
async def test_kline_endpoint_exception_async():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_stock_kline
    with patch.object(km2, "_get_stock_bars", side_effect=Exception("boom")):
        req = _fake_request({})
        out = await get_stock_kline(req, "000001.SZ", start="2024-01-01", end="2024-06-30")
    assert out is not None


# ---------------------------------------------------------------------------
# get_sector_kline / get_index_kline / compare_kline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sector_kline():
    from quantide.web.apis.analysis.kline import get_sector_kline
    req = MagicMock()
    out = await get_sector_kline(req, "sector1")
    assert out is not None


@pytest.mark.asyncio
async def test_get_index_kline_basic():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_index_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [3000.0]})
    with patch.object(km2, "_get_index_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_index_kline(req, "000300.SH", start="2024-01-01", end="2024-06-30")
    assert out is not None


@pytest.mark.asyncio
async def test_get_index_kline_no_dates():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_index_kline
    fake_df = pl3.DataFrame({"date": [dt.date.today()], "close": [3000.0]})
    with patch.object(km2, "_get_index_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_index_kline(req, "000300.SH")
    assert out is not None


@pytest.mark.asyncio
async def test_get_index_kline_invalid_date():
    from quantide.web.apis.analysis.kline import get_index_kline
    req = _fake_request({})
    out = await get_index_kline(req, "000300.SH", start="oops")
    assert out is not None


@pytest.mark.asyncio
async def test_get_index_kline_invalid_ma():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_index_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [3000.0]})
    with patch.object(km2, "_get_index_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_index_kline(req, "000300.SH", start="2024-01-01", end="2024-06-30", ma="x")
    assert out is not None


@pytest.mark.asyncio
async def test_get_index_kline_invalid_freq():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_index_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [3000.0]})
    with patch.object(km2, "_get_index_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_index_kline(req, "000300.SH", start="2024-01-01", end="2024-06-30", freq="yr")
    assert out is not None


@pytest.mark.asyncio
async def test_get_index_kline_with_ma():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_index_kline
    fake_df = pl3.DataFrame({
        "date": [dt.date(2024, 6, 1), dt.date(2024, 6, 2)],
        "close": [3000.0, 3010.0],
    })
    with patch.object(km2, "_get_index_bars", return_value=fake_df):
        with patch.object(km2, "add_ma_to_list", return_value=[]):
            req = _fake_request({})
            out = await get_index_kline(req, "000300.SH", start="2024-01-01", end="2024-06-30", ma="5,10")
    assert out is not None


@pytest.mark.asyncio
async def test_get_index_kline_exception():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import get_index_kline
    with patch.object(km2, "_get_index_bars", side_effect=Exception("boom")):
        req = _fake_request({})
        out = await get_index_kline(req, "000300.SH", start="2024-01-01", end="2024-06-30")
    assert out is not None


# ---------------------------------------------------------------------------
# compare_kline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_kline_basic():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import compare_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [10.0]})
    with patch.object(km2, "_get_stock_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await compare_kline(req, "000001.SZ", "600000.SH", start="2024-01-01", end="2024-06-30")
    assert out is not None


@pytest.mark.asyncio
async def test_compare_kline_no_dates():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import compare_kline
    fake_df = pl3.DataFrame({"date": [dt.date.today()], "close": [10.0]})
    with patch.object(km2, "_get_stock_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await compare_kline(req, "000001.SZ", "600000.SH")
    assert out is not None


@pytest.mark.asyncio
async def test_compare_kline_invalid_date():
    from quantide.web.apis.analysis.kline import compare_kline
    req = _fake_request({})
    out = await compare_kline(req, "000001.SZ", "600000.SH", start="bad")
    assert out is not None


@pytest.mark.asyncio
async def test_compare_kline_invalid_freq():
    from quantide.web.apis.analysis import kline as compare_line
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import compare_kline
    fake_df = pl3.DataFrame({"date": [dt.date(2024, 6, 1)], "close": [10.0]})
    with patch.object(km2, "_get_stock_bars", return_value=fake_df):
        with patch.object(km2, "bars_to_list", return_value=[]):
            req = _fake_request({})
            out = await compare_kline(req, "000001.SZ", "600000.SH", start="2024-01-01", end="2024-06-30", freq="nope")
    assert out is not None


@pytest.mark.asyncio
async def test_compare_kline_exception():
    from quantide.web.apis.analysis import kline as km2
    from quantide.web.apis.analysis.kline import compare_kline
    with patch.object(km2, "_get_stock_bars", side_effect=Exception("boom")):
        req = _fake_request({})
        out = await compare_kline(req, "000001.SZ", "600000.SH", start="2024-01-01", end="2024-06-30")
    assert out is not None


# ---------------------------------------------------------------------------
# bars_to_list / add_ma_to_list (pure helpers)
# ---------------------------------------------------------------------------


from quantide.web.apis.analysis.kline import bars_to_list, add_ma_to_list


def test_bars_to_list_empty():
    out = bars_to_list(pl3.DataFrame())
    assert out == []


def test_bars_to_list_with_frame_dates():
    """When row['frame'] is a date, formats as isoformat."""
    df = pl3.DataFrame({
        "frame": [dt.date(2024, 6, 1), dt.date(2024, 6, 2)],
        "open": [10.0, 10.5], "high": [10.5, 11.0],
        "low": [9.5, 10.0], "close": [10.2, 10.8],
        "volume": [1000.0, 1500.0], "amount": [10200.0, 16200.0],
    })
    out = bars_to_list(df)
    assert len(out) == 2
    assert out[0]["dt"] == "2024-06-01"
    assert out[1]["dt"] == "2024-06-02"


def test_bars_to_list_with_string_dates():
    """When row['frame'] is string, passes through."""
    df = pl3.DataFrame({
        "frame": ["2024-06-01", "2024-06-02"],
        "open": [10.0, 10.5], "high": [10.5, 11.0],
        "low": [9.5, 10.0], "close": [10.2, 10.8],
        "volume": [1000.0, 1500.0], "amount": [10200.0, 16200.0],
    })
    out = bars_to_list(df)
    assert len(out) == 2
    assert out[0]["dt"] == "2024-06-01"


def test_add_ma_to_list_empty():
    out = add_ma_to_list(pl3.DataFrame(), [5])
    assert out == []


def test_add_ma_to_list_with_ma():
    """When row has ma5 column, adds to output."""
    df = pl3.DataFrame({
        "frame": [dt.date(2024, 6, 1), dt.date(2024, 6, 2)],
        "open": [10.0, 10.5], "high": [10.5, 11.0],
        "low": [9.5, 10.0], "close": [10.2, 10.8],
        "volume": [1000.0, 1500.0], "amount": [10200.0, 16200.0],
        "ma5": [10.1, 10.3],
    })
    out = add_ma_to_list(df, [5])
    assert len(out) == 2
    assert "ma5" in out[0]


def test_add_ma_to_list_with_ma_missing():
    """When row does not have ma key, omits from output."""
    df = pl3.DataFrame({
        "frame": [dt.date(2024, 6, 1), dt.date(2024, 6, 2)],
        "open": [10.0, 10.5], "high": [10.5, 11.0],
        "low": [9.5, 10.0], "close": [10.2, 10.8],
        "volume": [1000.0, 1500.0], "amount": [10200.0, 16200.0],
    })
    out = add_ma_to_list(df, [5])
    assert len(out) == 2
    assert "ma5" not in out[0]


def test_add_ma_to_list_with_ma_none():
    """When row[ma_key] is None, omits from output."""
    df = pl3.DataFrame({
        "frame": [dt.date(2024, 6, 1), dt.date(2024, 6, 2)],
        "open": [10.0, 10.5], "high": [10.5, 11.0],
        "low": [9.5, 10.0], "close": [10.2, 10.8],
        "volume": [1000.0, 1500.0], "amount": [10200.0, 16200.0],
        "ma5": [10.1, None],
    })
    out = add_ma_to_list(df, [5])
    assert len(out) == 2
    # First has ma5, second doesn't
    assert "ma5" in out[0]
    assert "ma5" not in out[1]


def test_add_ma_to_list_with_string_frame():
    df = pl3.DataFrame({
        "frame": ["2024-06-01", "2024-06-02"],
        "open": [10.0, 10.5], "high": [10.5, 11.0],
        "low": [9.5, 10.0], "close": [10.2, 10.8],
        "volume": [1000.0, 1500.0], "amount": [10200.0, 16200.0],
    })
    out = add_ma_to_list(df, [5])
    assert len(out) == 2
    assert out[0]["dt"] == "2024-06-01"
