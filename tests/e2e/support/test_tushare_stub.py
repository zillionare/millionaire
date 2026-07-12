"""Tests for the fixture-backed Tushare stub."""

from __future__ import annotations

import datetime

import pytest

from tests.e2e.support.tushare_stub import TushareStubConfig, patched_tushare_fetcher


def test_tushare_stub_serves_fixture_backed_market_data() -> None:
    with patched_tushare_fetcher() as fetcher:
        calendar = fetcher.fetch_calendar(datetime.date(2024, 1, 1))
        stocks = fetcher.fetch_stock_list()
        bars, errors = fetcher.fetch_bars_ext(datetime.date(2024, 1, 2))

    assert errors == []
    assert len(calendar) > 200
    assert stocks is not None
    assert len(stocks) > 5000
    pingan = stocks.loc[stocks["asset"] == "000001.SZ"].iloc[0]
    assert pingan["name"] == "平安银行"
    assert pingan["pinyin"] == "PAYH"
    assert set(bars.columns) == {
        "date",
        "asset",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adjust",
        "is_st",
        "up_limit",
        "down_limit",
    }
    assert not bars.empty


@pytest.mark.parametrize(
    ("config", "endpoint", "expected_exception"),
    [
        (TushareStubConfig(rate_limited_endpoints={"daily"}), "daily", RuntimeError),
        (TushareStubConfig(auth_failed_endpoints={"stock_basic"}), "stock_basic", PermissionError),
        (TushareStubConfig(network_failed_endpoints={"trade_cal"}), "trade_cal", ConnectionError),
    ],
)
def test_tushare_stub_supports_failure_injection(
    config: TushareStubConfig,
    endpoint: str,
    expected_exception: type[Exception],
) -> None:
    with patched_tushare_fetcher(config=config) as fetcher:
        with pytest.raises(expected_exception):
            if endpoint == "daily":
                fetcher.fetch_bars(datetime.date(2024, 1, 2))
            elif endpoint == "stock_basic":
                fetcher.fetch_stock_list()
            else:
                fetcher.fetch_calendar(datetime.date(2024, 1, 1))


def test_tushare_stub_supports_empty_data_and_missing_fields() -> None:
    with patched_tushare_fetcher(
        config=TushareStubConfig(
            empty_endpoints={"stock_st"},
            missing_fields={"daily": ("amount",)},
        )
    ) as fetcher:
        st_info, st_errors = fetcher.fetch_st_info(datetime.date(2024, 1, 2))
        bars, bar_errors = fetcher.fetch_bars(datetime.date(2024, 1, 2))

    assert st_errors == []
    assert bar_errors == []
    assert st_info.empty
    assert "amount" not in bars.columns
