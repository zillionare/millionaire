"""BaoStock 分钟线抓取器的预算与黑名单逻辑测试。"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from quantide.data.fetchers.baostock_minute import (
    BaostockMinuteFetcher,
    BaostockThrottledError,
)


@pytest.fixture(autouse=True)
def isolated_budget(tmp_path, monkeypatch):
    monkeypatch.setattr("quantide.data.fetchers.baostock_minute.get_app_config_dir", lambda: tmp_path)


def test_code_conversion():
    """统一代码转 BaoStock 格式。"""
    f = BaostockMinuteFetcher()
    assert f._to_baostock_code("600000.SH") == "sh.600000"
    assert f._to_baostock_code("000001.SZ") == "sz.000001"
    assert f._to_baostock_code("688111.SH") == "sh.688111"


def test_daily_budget_stops_requests():
    """超出每日预算后拒绝继续请求。"""
    fetcher = BaostockMinuteFetcher(daily_budget=2)
    fetcher._consume()
    fetcher._consume()
    assert fetcher.budget_remaining == 0
    with pytest.raises(BaostockThrottledError, match="预算"):
        fetcher._check_budget()


def test_blacklist_error_marks_freeze_window():
    """命中限频关键词后标记 6 小时冻结。"""
    fetcher = BaostockMinuteFetcher()
    with pytest.raises(BaostockThrottledError, match="黑名单"):
        fetcher._handle_error("抱歉，您访问接口(stk_mins)频率超限(1次/分钟)")
    from quantide.core.market_time import market_now
    until = datetime.datetime.fromisoformat(fetcher._budget.status()["blocked_until"])
    delta = until - market_now()
    assert 6.0 <= timedelta_hours(delta) <= 6.1


def timedelta_hours(delta: datetime.timedelta) -> float:
    """时间差的小时数。"""
    return delta.total_seconds() / 3600


def test_blacklisted_fetcher_refuses_requests():
    """冻结期内直接拒绝。"""
    fetcher = BaostockMinuteFetcher()
    fetcher._budget.freeze()
    with pytest.raises(BaostockThrottledError, match="黑名单"):
        fetcher._check_budget()


def test_non_blocking_error_does_not_freeze():
    """普通错误不触发冻结。"""
    fetcher = BaostockMinuteFetcher()
    with pytest.raises(BaostockThrottledError, match="请求失败"):
        fetcher._handle_error("网络连接失败")
    assert fetcher._budget.status().get("blocked_until") is None


def test_fetch_minute_bars_normalizes_fields():
    """抓取结果字段归一化。"""
    baostock = pytest.importorskip(
        "baostock", reason="BaoStock is installed only with the optional ml30m extra"
    )
    fetcher = BaostockMinuteFetcher()
    raw = MagicMock()
    raw.error_code = "0"
    raw.error_msg = "success"
    raw.fields = [
        "date",
        "time",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]
    raw.next.side_effect = [
        True,
        True,
        False,
    ]
    raw.get_row_data.side_effect = [
        [
            "2024-07-01",
            "20240701100000000",
            "sh.600000",
            "8.22",
            "8.26",
            "8.21",
            "8.25",
            "4708600",
            "38809648.0000",
        ],
        [
            "2024-07-01",
            "20240701103000000",
            "sh.600000",
            "8.25",
            "8.27",
            "8.23",
            "8.24",
            "4850800",
            "40038984.0000",
        ],
    ]

    with patch.object(baostock, "login") as mock_login, patch.object(
        baostock, "query_history_k_data_plus", return_value=raw
    ):
        mock_login.return_value = MagicMock(error_code="0", error_msg="success")
        frame = fetcher.fetch_minute_bars(
            "600000.SH", datetime.date(2024, 7, 1), datetime.date(2024, 7, 5)
        )

    assert len(frame) == 2
    assert frame["asset"].tolist() == ["600000.SH", "600000.SH"]
    assert frame["close"].tolist() == [8.25, 8.24]
    assert "dt" in frame.columns
    assert frame["date"].tolist() == [datetime.date(2024, 7, 1)] * 2


def test_min_history_date_is_clamped():
    """早于分钟线可用起点的时间会被收敛。"""
    baostock = pytest.importorskip(
        "baostock", reason="BaoStock is installed only with the optional ml30m extra"
    )
    fetcher = BaostockMinuteFetcher(min_history_date=datetime.date(2020, 1, 2))
    captured: dict = {}

    raw = MagicMock()
    raw.error_code = "0"
    raw.error_msg = "success"
    raw.fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]
    raw.next.side_effect = [False]
    raw.get_row_data.side_effect = []

    def _capture(code, fields, start_date, end_date, frequency, adjustflag):
        captured["start"] = start_date
        return raw

    with patch.object(baostock, "login") as mock_login, patch.object(
        baostock, "query_history_k_data_plus", side_effect=_capture
    ):
        mock_login.return_value = MagicMock(error_code="0", error_msg="success")
        fetcher.fetch_minute_bars(
            "600000.SH", datetime.date(2015, 1, 1), datetime.date(2015, 12, 31)
        )

    assert captured["start"] == "2020-01-02"
