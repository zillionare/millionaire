"""腾讯数据源适配器的单元测试（离线，使用假 HTTP 会话）。"""

from __future__ import annotations

import datetime
import json

import pandas as pd

from quantide.data.fetchers.tencent import TencentDataFetcher


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, quote_text: str = "", kline: dict | None = None) -> None:
        self.quote_text = quote_text
        self.kline = kline or {}
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, params=None, timeout=None):  # noqa: ANN001
        self.calls.append((url, params))
        if "qt.gtimg.cn" in url:
            return _FakeResponse(self.quote_text.encode("gbk"))
        return _FakeResponse(json.dumps(self.kline).encode("utf-8"))


def _quote_line(
    symbol: str = "sh600519",
    price: str = "10.0",
    prev_close: str = "9.9",
    open_price: str = "9.95",
    volume: str = "1000",
    high: str = "10.2",
    low: str = "9.9",
    amount_wan: str = "500",
    up: str = "11.0",
    down: str = "9.0",
) -> str:
    fields = [""] * 49
    fields[0] = "1"
    fields[1] = "贵州茅台"
    fields[2] = symbol[2:]
    fields[3] = price
    fields[4] = prev_close
    fields[5] = open_price
    fields[6] = volume
    fields[30] = "20241022150000"
    fields[33] = high
    fields[34] = low
    fields[37] = amount_wan
    fields[47] = up
    fields[48] = down
    return f'v_{symbol}="{"~".join(fields)}";'


def test_fetch_quote_snapshot_parses_price_limits_and_units():
    """实时快照解析：价格、涨跌停、成交额（万元→千元）。"""
    session = _FakeSession(quote_text=_quote_line())
    fetcher = TencentDataFetcher(access_check=lambda: None, session=session)

    snapshot = fetcher.fetch_quote_snapshot(["600519.SH"])

    assert "600519.SH" in snapshot
    quote = snapshot["600519.SH"]
    assert quote["name"] == "贵州茅台"
    assert quote["price"] == 10.0
    assert quote["prev_close"] == 9.9
    assert quote["open"] == 9.95
    assert quote["high"] == 10.2
    assert quote["low"] == 9.9
    assert quote["volume"] == 1000.0
    # 源字段 500 万元 -> 5000 千元（与 Tushare daily.amount 口径一致）
    assert quote["amount"] == 5000.0
    assert quote["up_limit"] == 11.0
    assert quote["down_limit"] == 9.0
    assert quote["ts"] == datetime.datetime(2024, 10, 22, 15, 0)


def test_fetch_quote_snapshot_skips_suspended_symbols():
    """停牌/无价格的标的应被跳过。"""
    session = _FakeSession(quote_text=_quote_line(price="0"))
    fetcher = TencentDataFetcher(access_check=lambda: None, session=session)
    assert fetcher.fetch_quote_snapshot(["600519.SH"]) == {}


def test_fetch_minute_bars_maps_tencent_column_order():
    """腾讯 K 线行顺序是 [日期, 开, 收, 高, 低, 量]，需正确映射。"""
    kline = {
        "data": {
            "sh600519": {
                "m30": [
                    ["2024-01-02 09:30", "10.0", "10.5", "10.6", "9.9", "1000"],
                    ["2024-01-02 10:00", "10.5", "10.4", "10.7", "10.2", "2000"],
                ]
            }
        }
    }
    fetcher = TencentDataFetcher(access_check=lambda: None, session=_FakeSession(kline=kline))

    frame, errors = fetcher.fetch_minute_bars(
        "600519.SH", period="30", count=320
    )

    assert errors == []
    assert len(frame) == 2
    first = frame.iloc[0].to_dict()
    assert first["open"] == 10.0
    assert first["close"] == 10.5
    assert first["high"] == 10.6
    assert first["low"] == 9.9
    assert first["volume"] == 1000.0
    assert first["amount"] == 1050.0  # 1000 手 * 10.5 元 / 10 = 1050 千元
    assert str(frame["date"].dtype) == "datetime64[ms]"


def test_fetch_minute_bars_filters_date_range():
    """start/end 过滤生效。"""
    kline = {
        "data": {
            "sh600519": {
                "m30": [
                    ["2024-01-02 09:30", "10.0", "10.5", "10.6", "9.9", "1000"],
                    ["2024-02-01 09:30", "11.0", "11.5", "11.6", "10.9", "1000"],
                ]
            }
        }
    }
    fetcher = TencentDataFetcher(access_check=lambda: None, session=_FakeSession(kline=kline))
    frame, _ = fetcher.fetch_minute_bars(
        "600519.SH",
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        period="30",
    )
    assert len(frame) == 1
    assert frame["date"][0].date() == datetime.date(2024, 1, 2)


def test_fetch_index_bars_filters_and_labels_index_code():
    """指数日线使用腾讯日 K，并标注 index_code。"""
    kline = {
        "data": {
            "sh000300": {
                "qfqday": [
                    ["2024-01-02", "3000", "3005", "3010", "2990", "100000"],
                    ["2024-06-28", "3100", "3105", "3110", "3090", "100000"],
                ]
            }
        }
    }
    fetcher = TencentDataFetcher(access_check=lambda: None, session=_FakeSession(kline=kline))
    frame, errors = fetcher.fetch_index_bars(
        ["000300.SH"], datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
    )
    assert errors == []
    assert len(frame) == 1
    row = frame.iloc[0].to_dict()
    assert row["index_code"] == "000300.SH"
    assert row["close"] == 3005.0
    assert not pd.isna(frame["close"]).any()
