"""实时行情页面渲染测试。"""

from __future__ import annotations

import datetime

from fasthtml.common import to_xml

from quantide.web.pages.system import realtime


class _FakeQuotes:
    def __init__(self, rows=None, last=None) -> None:
        self._rows = rows or []
        self._last = last

    def status(self):
        return {
            "started": True,
            "symbols": len(self._rows),
            "messages": 3,
            "updates": len(self._rows),
            "last_received_at": self._last,
            "last_batch_at": self._last,
            "last_batch_size": len(self._rows),
        }

    def snapshot(self, query="", limit=50):
        return self._rows[:limit]


def test_realtime_content_renders_quotes(monkeypatch):
    now = datetime.datetime(2024, 1, 3, 10, 0)
    monkeypatch.setattr(realtime, "_is_session", lambda current: True)
    monkeypatch.setattr(
        realtime,
        "quote_monitor",
        _FakeQuotes(
            rows=[
                {
                    "symbol": "600519.SH",
                    "name": "贵州茅台",
                    "price": 1334.0,
                    "prev_close": 1335.0,
                    "volume": 100.0,
                    "amount": 2000.0,
                    "quote_ts": now,
                    "received_at": now,
                }
            ],
            last=now,
        ),
    )
    html = to_xml(realtime._render_content(now, ""))
    assert "实时行情" in html
    assert "hx-trigger" in html
    assert "every 3s" in html
    assert "600519.SH" in html
    assert "贵州茅台" in html
    assert "实时" in html
    assert "MessageHub" not in html
    assert "查看风险事件" not in html


def test_realtime_content_empty_state(monkeypatch):
    monkeypatch.setattr(realtime, "_is_session", lambda current: True)
    monkeypatch.setattr(realtime, "quote_monitor", _FakeQuotes(rows=[], last=None))
    html = to_xml(realtime._render_content(datetime.datetime(2024, 1, 3, 10, 0), ""))
    assert "尚未收到行情" in html
    assert "QUANTIDE_QUOTE_PUBLISHER" not in html
    assert "查看风险事件" not in html


def test_realtime_filter_survives_polling(monkeypatch):
    """轮询时必须携带筛选输入，避免下一次刷新覆盖用户输入。"""
    now = datetime.datetime(2024, 1, 3, 10, 0)
    monkeypatch.setattr(realtime, "_is_session", lambda current: True)
    monkeypatch.setattr(
        realtime,
        "quote_monitor",
        _FakeQuotes(
            rows=[
                {
                    "symbol": "600519.SH",
                    "name": "贵州茅台",
                    "price": 1334.0,
                    "prev_close": 1335.0,
                    "volume": 100.0,
                    "amount": 2000.0,
                    "quote_ts": now,
                    "received_at": now,
                }
            ],
            last=now,
        ),
    )
    html = to_xml(realtime._render_content(now, "600519"))
    assert 'value="600519"' in html
    assert 'id="realtime-filter"' in html
    assert 'hx-include="#realtime-filter"' in html


def test_realtime_breadcrumb_is_left_aligned():
    from fasthtml.common import to_xml

    html = to_xml(realtime._breadcrumb())
    assert "justify-start" in html
    assert "w-fit" in html


def test_realtime_limit_badge_uses_clear_text(monkeypatch):
    now = datetime.datetime(2024, 1, 3, 10, 0)
    monkeypatch.setattr(realtime, "_is_session", lambda current: True)
    monkeypatch.setattr(realtime, "quote_monitor", _FakeQuotes(rows=[], last=None))

    class _Limits:
        def limits_map(self, _dt):
            return {"600519.SH": (100.0, 120.0), "000001.SZ": (10.0, 12.0)}

    class _Stocks:
        size = 4

    monkeypatch.setattr("quantide.data.get_limit_price_store", lambda: _Limits())
    monkeypatch.setattr(realtime, "stock_list", _Stocks())
    html = to_xml(realtime._render_content(now, ""))
    assert "涨跌停价已获取：2/4（50%）" in html


def test_realtime_post_market_uses_latest_persisted_snapshot(monkeypatch, tmp_path):
    """休市时忽略实时缓存，展示冻结的最近持久化快照且停止轮询。"""
    now = datetime.datetime(2024, 1, 3, 16, 0)
    monkeypatch.setattr(realtime, "_is_session", lambda current: False)
    live = {
        "symbol": "000001.SZ",
        "name": "平安银行",
        "price": 11.0,
        "prev_close": 10.0,
        "volume": 1.0,
        "amount": 1.0,
        "quote_ts": now,
        "received_at": now,
    }
    monkeypatch.setattr(realtime, "quote_monitor", _FakeQuotes(rows=[live], last=now))
    snapshots = tmp_path / "market-snapshots"
    snapshots.mkdir()
    (snapshots / "2024-01-03.json").write_text(
        """{
  "captured_at": "2024-01-03T15:00:30+08:00",
  "quotes": [
    {
      "symbol": "600519.SH",
      "name": "贵州茅台",
      "price": 1334.0,
      "prev_close": 1335.0,
      "volume": 100.0,
      "amount": 2000.0,
      "quote_ts": "2024-01-03T14:59:00+08:00",
      "received_at": "2024-01-03T15:00:00+08:00"
    }
  ]
}""",
        encoding="utf-8",
    )
    monkeypatch.setattr(realtime, "get_app_config_dir", lambda: tmp_path)
    html = to_xml(realtime._render_content(now, ""))
    assert "600519.SH" in html
    assert "贵州茅台" in html
    assert "000001.SZ" not in html
    assert "休市" in html
    assert "15:00:30" in html
    assert "30.0s" in html
    assert "hx-trigger" not in html
    assert "尚未收到行情" not in html
    assert "暂无最近行情数据" not in html
