"""B08-kline-api: Test kline.py simple utilities + feature_removed."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest

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
