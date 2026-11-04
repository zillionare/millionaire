"""多数据源聚合器的单元测试（离线）。"""

from __future__ import annotations

import datetime

import pandas as pd

from quantide.core.ports.data_fetcher import (
    STANDARD_BAR_COLUMNS,
    STANDARD_MINUTE_BAR_COLUMNS,
)
from quantide.data.fetchers.multi import BaostockMinuteAdapter, MultiSourceDataFetcher


def _daily_frame(asset: str = "600519.SH", close: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-02"),
                "asset": asset,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 100.0,
                "amount": 1000.0,
                "adjust": 1.0,
                "is_st": False,
                "up_limit": 0.0,
                "down_limit": 0.0,
            }
        ]
    )[STANDARD_BAR_COLUMNS]


def _minute_frame(asset: str = "600519.SH") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-02 09:30"),
                "asset": asset,
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "close": 10.2,
                "volume": 100.0,
                "amount": 1020.0,
            }
        ]
    )[STANDARD_MINUTE_BAR_COLUMNS]


class _FakeFetcher:
    source_name = "fake"

    def __init__(
        self,
        daily: pd.DataFrame | None = None,
        index: pd.DataFrame | None = None,
        minute: pd.DataFrame | None = None,
        quotes: dict | None = None,
        fail: bool = False,
    ) -> None:
        self.daily = daily if daily is not None else pd.DataFrame()
        self.index = index if index is not None else pd.DataFrame()
        self.minute = minute if minute is not None else pd.DataFrame()
        self.quotes = quotes or {}
        self.fail = fail

    def fetch_bars(self, dates):
        if self.fail:
            raise RuntimeError("boom")
        return self.daily, []

    def fetch_index_bars(self, codes, start_date, end_date):
        if self.fail:
            raise RuntimeError("boom")
        return self.index, []

    def fetch_minute_bars(
        self,
        asset,
        start_date=None,
        end_date=None,
        period="30",
        count=320,
    ):
        if self.fail:
            raise RuntimeError("boom")
        return self.minute, []

    def fetch_quote_snapshot(self, symbols):
        return self.quotes


class _LegacyBaostock:
    source_name = "baostock"

    def fetch_minute_bars(self, asset, start_date, end_date, frequency="30", adjust="3"):
        return pd.DataFrame(
            [
                {
                    "dt": datetime.datetime(2024, 1, 2, 9, 30),
                    "asset": asset,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.9,
                    "close": 10.2,
                    "volume": 100.0,
                    "amount": 1020.0,
                }
            ]
        )


def test_daily_bars_prefers_primary_source():
    """主源有数据时不走补充源。"""
    primary = _FakeFetcher(daily=_daily_frame(close=10.0))
    backup = _FakeFetcher(daily=_daily_frame(close=20.0))
    multi = MultiSourceDataFetcher(
        fetchers={"tushare": primary, "tencent": backup},
        stages={"daily_bars": ["tushare", "tencent"]},
    )
    frame, errors = multi.fetch_bars(datetime.date(2024, 1, 2))
    assert errors == []
    assert frame.iloc[0]["close"] == 10.0


def test_daily_bars_falls_back_when_primary_fails():
    """主源异常时自动降级到腾讯。"""
    primary = _FakeFetcher(fail=True)
    backup = _FakeFetcher(daily=_daily_frame(close=20.0))
    multi = MultiSourceDataFetcher(
        fetchers={"tushare": primary, "tencent": backup},
        stages={"daily_bars": ["tushare", "tencent"]},
    )
    frame, errors = multi.fetch_bars(datetime.date(2024, 1, 2))
    assert not frame.empty
    assert frame.iloc[0]["close"] == 20.0
    assert errors and errors[0][0] == "tushare"


def test_daily_bars_all_sources_fail_preserves_errors_and_return_shape():
    multi = MultiSourceDataFetcher(
        fetchers={"first": _FakeFetcher(fail=True), "second": _FakeFetcher(fail=True)},
        stages={"daily_bars": ["first", "second"]},
    )
    frame, errors = multi.fetch_bars(datetime.date(2024, 1, 2))
    assert frame.empty
    assert [error[0] for error in errors] == ["first", "second"]


def test_daily_bars_without_source_reports_unavailability():
    multi = MultiSourceDataFetcher(stages={"daily_bars": []})
    frame, errors = multi.fetch_bars(datetime.date(2024, 1, 2))
    assert frame.empty
    assert errors == [["daily_bars", "fetch_bars", "no available data source"]]


def test_minute_bars_falls_back_to_baostock():
    """腾讯无分钟数据时用 BaoStock 历史补齐。"""
    tencent = _FakeFetcher(minute=pd.DataFrame())
    baostock = BaostockMinuteAdapter(_LegacyBaostock())
    multi = MultiSourceDataFetcher(
        fetchers={"tencent": tencent, "baostock": baostock},
        stages={"minute_bars": ["tencent", "baostock"]},
    )
    frame, errors = multi.fetch_minute_bars(
        "600519.SH",
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        period="30",
    )
    assert errors == []
    assert list(frame.columns) == STANDARD_MINUTE_BAR_COLUMNS
    assert frame.iloc[0]["close"] == 10.2


def test_index_bars_falls_back_to_tencent():
    """指数日线主源失败时回落到腾讯。"""
    primary = _FakeFetcher(fail=True)
    backup = _FakeFetcher(
        index=pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2024-01-02"),
                    "index_code": "000300.SH",
                    "open": 3000.0,
                    "high": 3010.0,
                    "low": 2990.0,
                    "close": 3005.0,
                    "volume": 100.0,
                    "amount": 0.0,
                }
            ]
        )
    )
    multi = MultiSourceDataFetcher(
        fetchers={"tushare": primary, "tencent": backup},
        stages={"index_bars": ["tushare", "tencent"]},
    )
    frame, errors = multi.fetch_index_bars(
        ["000300.SH"], datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
    )
    assert not frame.empty
    assert frame.iloc[0]["close"] == 3005.0
    assert errors and errors[0][0] == "tushare"


def test_quote_snapshot_uses_tencent():
    """实时快照路由到腾讯。"""
    tencent = _FakeFetcher(quotes={"600519.SH": {"price": 10.0}})
    multi = MultiSourceDataFetcher(
        fetchers={"tencent": tencent},
        stages={"quote_snapshot": ["tencent"]},
    )
    assert multi.fetch_quote_snapshot(["600519.SH"])["600519.SH"]["price"] == 10.0
