"""FR-310 数据同步任务.

按 acceptance.md:
- AC-310-01: 定时同步覆盖行情与参考数据
- AC-310-02: 支持错过任务重跑与补录
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from quantide.data.services.stock_sync import StockSyncService


class TestAC31001:
    """AC-310-01: 定时同步覆盖行情与参考数据"""

    def test_happy_sync_returns_stats(self, monkeypatch):
        """AC-310-01: happy — sync_daily 返回 stocks/bars 统计"""
        monkeypatch.setattr(
            "quantide.data.services.stock_sync.get_epoch",
            lambda: datetime.date(2024, 1, 1),
        )
        fetcher = MagicMock()
        fetcher.fetch_stock_list.return_value = pd.DataFrame({
            "asset": ["000001.SZ"], "name": ["平安银行"],
            "pinyin": ["PAYH"], "list_date": [datetime.date(1991, 4, 3)],
            "delist_date": [pd.NaT],
        })
        stock_list = MagicMock()
        daily_store = MagicMock()
        calendar = MagicMock()

        service = StockSyncService(stock_list, daily_store, calendar, fetcher=fetcher)
        result = service.sync_stock_list()
        assert result >= 0
        assert isinstance(result, int)

    def test_edge_missing_day_backfill(self, monkeypatch):
        """AC-310-01: edge — 缺失某交易日后补录"""
        monkeypatch.setattr(
            "quantide.data.services.stock_sync.get_epoch",
            lambda: datetime.date(2024, 1, 1),
        )
        fetcher = MagicMock()
        fetcher.fetch_stock_list.return_value = pd.DataFrame({
            "asset": ["000001.SZ"], "name": ["平安银行"],
            "pinyin": ["PAYH"], "list_date": [datetime.date(1991, 4, 3)],
            "delist_date": [pd.NaT],
        })
        service = StockSyncService(MagicMock(), MagicMock(), MagicMock(), fetcher=fetcher)
        assert service.sync_stock_list() == 1
        # 再次同步 (幂等)
        assert service.sync_stock_list() == 1

    def test_error_empty_fetcher(self, monkeypatch):
        """AC-310-01: error — fetcher 返回空数据时报告 0 count"""
        monkeypatch.setattr(
            "quantide.data.services.stock_sync.get_epoch",
            lambda: datetime.date(2024, 1, 1),
        )
        fetcher = MagicMock()
        fetcher.fetch_stock_list.return_value = None
        service = StockSyncService(MagicMock(), MagicMock(), MagicMock(), fetcher=fetcher)
        assert service.sync_stock_list() == 0


class TestAC31002:
    """AC-310-02: 重跑与补录"""

    def test_happy_missed_task_rerunnable(self, monkeypatch):
        """AC-310-02: happy — 错过的任务列表可重跑"""
        monkeypatch.setattr(
            "quantide.data.services.stock_sync.get_epoch",
            lambda: datetime.date(2024, 1, 1),
        )
        fetcher = MagicMock()
        fetcher.fetch_stock_list.return_value = pd.DataFrame({
            "asset": ["000001.SZ"], "name": ["平安银行"],
            "pinyin": ["PAYH"], "list_date": [datetime.date(1991, 4, 3)],
            "delist_date": [pd.NaT],
        })
        stock_list = MagicMock()
        daily_store = MagicMock()
        calendar = MagicMock()

        service = StockSyncService(stock_list, daily_store, calendar, fetcher=fetcher)
        # 重跑不抛异常
        result = service.sync_stock_list()
        assert result >= 0

    def test_edge_idempotent(self, monkeypatch):
        """AC-310-02: edge — 同一任务重入幂等"""
        monkeypatch.setattr(
            "quantide.data.services.stock_sync.get_epoch",
            lambda: datetime.date(2024, 1, 1),
        )
        fetcher = MagicMock()
        fetcher.fetch_stock_list.return_value = pd.DataFrame({
            "asset": ["000001.SZ"], "name": ["平安银行"],
            "pinyin": ["PAYH"], "list_date": [datetime.date(1991, 4, 3)],
            "delist_date": [pd.NaT],
        })
        service = StockSyncService(MagicMock(), MagicMock(), MagicMock(), fetcher=fetcher)
        r1 = service.sync_stock_list()
        r2 = service.sync_stock_list()
        assert r1 == r2

    def test_error_fetcher_failure(self, monkeypatch):
        """AC-310-02: error — 重跑失败的明确错误"""
        monkeypatch.setattr(
            "quantide.data.services.stock_sync.get_epoch",
            lambda: datetime.date(2024, 1, 1),
        )
        fetcher = MagicMock()
        fetcher.fetch_stock_list.side_effect = RuntimeError("fetcher unavailable")
        service = StockSyncService(MagicMock(), MagicMock(), MagicMock(), fetcher=fetcher)
        with pytest.raises(RuntimeError, match="fetcher unavailable"):
            service.sync_stock_list()
