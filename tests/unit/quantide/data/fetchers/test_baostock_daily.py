"""Offline contract tests for the token-free BaoStock daily adapter."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantide.data.fetchers import baostock_minute
from quantide.data.fetchers.baostock_budget import BaostockThrottledError
from quantide.data.fetchers.baostock_daily import BaostockDailyFetcher
from quantide.data.fetchers.capabilities import supports_dataset

DAILY_FIELDS = [
    "date", "code", "open", "high", "low", "close", "preclose", "volume", "amount",
    "adjustflag", "tradestatus", "pctChg", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "isST",
]


class _Result:
    def __init__(self, fields: list[str], rows: list[list[str]], error: str = "") -> None:
        self.fields = fields
        self._rows = iter(rows)
        self.error_code = "1" if error else "0"
        self.error_msg = error

    def next(self) -> bool:
        try:
            self._next = next(self._rows)
        except StopIteration:
            return False
        return True

    def get_row_data(self) -> list[str]:
        return self._next


@pytest.fixture
def isolated_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(baostock_minute, "get_app_config_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def fake_baostock(monkeypatch):
    import baostock as bs

    monkeypatch.setattr(bs, "login", lambda: SimpleNamespace(error_code="0", error_msg=""))
    monkeypatch.setattr(bs, "logout", lambda: None)
    return bs


def test_daily_bars_ext_normalizes_units_and_st(fake_baostock, isolated_budget, monkeypatch) -> None:
    day = "2024-01-03"
    rows = [
        [day, "sh.600001", "10.00", "10.50", "9.90", "10.20", "9.80", "1000", "10200", "2", "1", "4.08", "", "", "", "", "0"],
        [day, "sz.000001", "20.00", "20.20", "19.80", "20.00", "19.90", "2000", "40000", "2", "1", "0.5", "", "", "", "", "1"],
    ]
    empty_adjust = _Result(["code", "dividOperateDate", "backAdjustFactor"], [])
    monkeypatch.setattr(
        fake_baostock,
        "query_daily_history_k_AStock",
        lambda **_kwargs: _Result(DAILY_FIELDS, rows),
    )
    monkeypatch.setattr(
        fake_baostock, "query_daily_adjust_factor", lambda **_kwargs: empty_adjust
    )

    frame, errors = BaostockDailyFetcher().fetch_bars_ext(datetime.date.fromisoformat(day))

    assert errors == []
    assert list(frame.columns) == [
        "date", "asset", "open", "high", "low", "close", "volume", "amount",
        "adjust", "is_st", "up_limit", "down_limit",
    ]
    first = frame[frame["asset"] == "600001.SH"].iloc[0]
    second = frame[frame["asset"] == "000001.SZ"].iloc[0]
    assert first["volume"] == pytest.approx(10.0)
    assert first["amount"] == pytest.approx(10.2)
    assert bool(first["is_st"]) is False
    assert bool(second["is_st"]) is True
    assert first["adjust"] == pytest.approx(1.0)
    assert pd.isna(first["up_limit"]) and pd.isna(first["down_limit"])


def test_daily_adjust_factor_merges_event_rows(fake_baostock, isolated_budget, monkeypatch) -> None:
    day = "2024-01-03"
    rows = [
        [day, "sh.600001", "10.00", "10.50", "9.90", "10.20", "9.80", "1000", "10200", "2", "1", "", "", "", "", "", "0"],
    ]
    adjust = _Result(
        ["code", "dividOperateDate", "backAdjustFactor"],
        [["sh.600001", day, "1.250000"]],
    )
    monkeypatch.setattr(
        fake_baostock, "query_daily_history_k_AStock", lambda **_kwargs: _Result(DAILY_FIELDS, rows)
    )
    monkeypatch.setattr(fake_baostock, "query_daily_adjust_factor", lambda **_kwargs: adjust)

    frame, errors = BaostockDailyFetcher().fetch_bars_ext(day)

    assert errors == []
    assert frame.iloc[0]["adjust"] == pytest.approx(1.25)


def test_calendar_and_stock_list_are_sqep_shaped(fake_baostock, isolated_budget, monkeypatch) -> None:
    calendar_result = _Result(
        ["calendar_date", "is_trading_day"],
        [["2024-01-01", "0"], ["2024-01-02", "1"], ["2024-01-03", "1"]],
    )
    stock_result = _Result(
        ["code", "code_name", "ipoDate", "outDate", "type", "status"],
        [
            ["sh.600001", "演示", "2018-01-02", "", "1", "1"],
            ["sh.000300", "指数", "2018-01-02", "", "2", "1"],
            ["bj.830001", "北交", "2020-01-02", "", "1", "1"],
        ],
    )
    monkeypatch.setattr(fake_baostock, "query_trade_dates", lambda **_kwargs: calendar_result)
    monkeypatch.setattr(fake_baostock, "query_stock_basic", lambda **_kwargs: stock_result)
    fetcher = BaostockDailyFetcher()

    calendar = fetcher.fetch_calendar(datetime.date(2024, 1, 1))
    stocks = fetcher.fetch_stock_list()

    assert list(calendar.columns) == ["is_open", "prev"]
    assert calendar.loc[datetime.date(2024, 1, 3), "prev"] == datetime.date(2024, 1, 2)
    assert stocks is not None
    assert stocks["asset"].to_list() == ["600001.SH"]
    assert pd.api.types.is_datetime64_any_dtype(pd.to_datetime(stocks["list_date"]))


def test_daily_bars_errors_are_separated_and_blacklist_freezes(
    fake_baostock, isolated_budget, monkeypatch
) -> None:
    day = datetime.date(2024, 1, 3)
    monkeypatch.setattr(
        fake_baostock,
        "query_daily_history_k_AStock",
        lambda **_kwargs: _Result(DAILY_FIELDS, [], error="频率超限"),
    )
    with pytest.raises(BaostockThrottledError, match="黑名单|频率|冻结"):
        BaostockDailyFetcher().fetch_bars(day)
    state = BaostockDailyFetcher()._budget.status()
    assert state["freezes"] == 1
    assert state["blocked_until"]


def test_baostock_capabilities_include_daily_but_not_market_cap() -> None:
    for dataset in ("daily_bars", "calendar", "stock_list", "adjust_factor", "st_info"):
        assert supports_dataset("baostock", dataset)
    assert not supports_dataset("baostock", "daily_basic")
    assert not supports_dataset("baostock", "index_weights")


def test_typed_empty_frames_never_fabricate_market_cap(
    fake_baostock, isolated_budget
) -> None:
    fetcher = BaostockDailyFetcher()
    basic, errors = fetcher.fetch_daily_basic(datetime.date(2024, 1, 3))
    limits, limit_errors = fetcher.fetch_limit_price(datetime.date(2024, 1, 3))
    assert errors == [] and limit_errors == []
    assert basic.empty and list(basic.columns) == ["date", "asset", "total_mv", "circ_mv"]
    assert limits.empty and list(limits.columns) == ["date", "asset", "up_limit", "down_limit"]
    assert np.isfinite(basic.shape[0])
