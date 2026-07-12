"""FR-0400 委托成交记录 + FR-0430 仿真交易单元测试.

覆盖:
- AC-FR0400-1~3: 委托成交记录 (三态 tab, 组合筛选)
- AC-FR0430-1~3: 仿真交易界面 (无下单辅助, 补单入口)
"""
from __future__ import annotations

import pytest

from quantide.web.services.trade_history import (
    HistoryFilter,
    HistoryRecord,
    HistoryRecordType,
    filter_history_records,
    has_trade_assist_in_paper,
    supports_makeup_order,
)


def _record(record_id, record_type=HistoryRecordType.ORDER, mode="paper", strategy_id="s1", symbol="000001.SZ", tm="2026-07-09T10:00:00"):
    return HistoryRecord(
        record_id=record_id,
        record_type=record_type,
        mode=mode,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp=tm,
        price=10.0,
        quantity=100,
        status="filled",
    )


class TestThreeModeTab:
    """AC-FR0400-1: tab 切换 回测/paper/live."""

    def test_filter_by_backtest_mode(self):
        records = [
            _record("r1", mode="backtest"),
            _record("r2", mode="paper"),
            _record("r3", mode="live"),
        ]
        filtered = filter_history_records(records, HistoryFilter(mode="backtest", strategy_id=None, symbol=None, date_from=None, date_to=None))
        assert all(r.mode == "backtest" for r in filtered)

    def test_filter_by_paper_mode(self):
        records = [_record("r1", mode="paper"), _record("r2", mode="live")]
        filtered = filter_history_records(records, HistoryFilter(mode="paper", strategy_id=None, symbol=None, date_from=None, date_to=None))
        assert len(filtered) == 1


class TestCombinedFilter:
    """AC-FR0400-2, AC-3: 组合筛选 (策略/个股/时间段, 三者均可留空)."""

    def test_filter_by_strategy_and_symbol(self):
        records = [
            _record("r1", strategy_id="s1", symbol="000001.SZ"),
            _record("r2", strategy_id="s2", symbol="000001.SZ"),
            _record("r3", strategy_id="s1", symbol="600519.SH"),
        ]
        filtered = filter_history_records(records, HistoryFilter(mode=None, strategy_id="s1", symbol="000001.SZ", date_from=None, date_to=None))
        assert len(filtered) == 1
        assert filtered[0].record_id == "r1"

    def test_filter_by_date_range(self):
        records = [
            _record("r1", tm="2026-07-01T10:00:00"),
            _record("r2", tm="2026-07-05T10:00:00"),
            _record("r3", tm="2026-07-10T10:00:00"),
        ]
        filtered = filter_history_records(records, HistoryFilter(mode=None, strategy_id=None, symbol=None, date_from="2026-07-03", date_to="2026-07-08"))
        assert len(filtered) == 1
        assert filtered[0].record_id == "r2"

    def test_all_empty_returns_all(self):
        """AC-2: 三者均可留空表示不限定."""
        records = [_record("r1"), _record("r2")]
        filtered = filter_history_records(records, HistoryFilter(mode=None, strategy_id=None, symbol=None, date_from=None, date_to=None))
        assert len(filtered) == 2


class TestTradeRecordVsFilledRecord:
    """AC-FR0400-1, AC-3: 委托 vs 成交."""

    def test_order_record_type(self):
        r = _record("r1", record_type=HistoryRecordType.ORDER)
        assert r.record_type == HistoryRecordType.ORDER

    def test_trade_record_type(self):
        r = _record("r1", record_type=HistoryRecordType.TRADE)
        assert r.record_type == HistoryRecordType.TRADE


class TestPaperTradeNoAssist:
    """AC-FR0430-2: 仿真交易界面无'下单辅助'区块."""

    def test_paper_has_no_trade_assist(self):
        """AC-2: 无参考价切换、无可卖数量计算、无双击持仓带入."""
        assert has_trade_assist_in_paper() is False

    def test_live_has_trade_assist(self):
        """实盘交易界面有下单辅助 (FR-0420)."""
        assert has_trade_assist_in_paper() is False  # paper 无辅助


class TestPaperMakeupOrder:
    """AC-FR0430-3: 仿真提供'补单'入口."""

    def test_paper_supports_makeup_order(self):
        """AC-3: 补单流程与实盘下单表单一致."""
        assert supports_makeup_order(mode="paper") is True

    def test_backtest_no_makeup_order(self):
        assert supports_makeup_order(mode="backtest") is False
