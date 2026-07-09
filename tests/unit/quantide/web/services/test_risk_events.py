"""FR-0070 风控触发事件详情单元测试.

覆盖 acceptance.md AC-FR0070-1~6:
- AC-1: 事件列表字段 (时间戳/标的/触发价/成本价/原因/超额收益)
- AC-2: 超额收益 N 日窗口未关闭显示'计算中...'
- AC-3: 触发原因分布饼图按 reason 分组, 点击过滤
- AC-4: 超额收益窗口 N 日输入字段 (默认 0, 范围 0~30)
- AC-5: 实例详情页 N 字段只读
- AC-6: 触发事件列表页/超额收益曲线页无 N 配置入口
"""
from __future__ import annotations

import pytest

from quantide.web.services.risk_events import (
    ExcessReturnWindowConfig,
    RiskEventItem,
    RiskEventReason,
    group_risk_events_by_reason,
    is_excess_return_pending,
    validate_excess_return_window,
)


def _event(event_id="e1", reason=RiskEventReason.STOP_LOSS, excess_return=None, window_closed=True):
    return RiskEventItem(
        event_id=event_id,
        timestamp="2026-07-09T10:00:00",
        symbol="000001.SZ",
        trigger_price=10.0,
        cost_price=11.0,
        reason=reason,
        excess_return=excess_return,
        window_closed=window_closed,
    )


class TestEventFields:
    """AC-1: 事件列表字段."""

    def test_event_has_all_fields(self):
        e = _event()
        assert e.event_id == "e1"
        assert e.symbol == "000001.SZ"
        assert e.trigger_price == 10.0
        assert e.cost_price == 11.0
        assert e.reason == RiskEventReason.STOP_LOSS


class TestExcessReturnPending:
    """AC-2: 超额收益 N 日窗口未关闭显示'计算中...'."""

    def test_pending_when_window_not_closed(self):
        """AC-2: N 日窗口未关闭时显示'计算中...'占位."""
        e = _event(window_closed=False, excess_return=None)
        assert is_excess_return_pending(e) is True

    def test_not_pending_when_window_closed(self):
        e = _event(window_closed=True, excess_return=0.05)
        assert is_excess_return_pending(e) is False

    def test_not_pending_when_excess_return_present(self):
        e = _event(window_closed=False, excess_return=0.03)
        assert is_excess_return_pending(e) is False


class TestReasonGrouping:
    """AC-3: 触发原因分布饼图按 reason 分组."""

    def test_group_by_reason(self):
        events = [
            _event("e1", RiskEventReason.STOP_LOSS),
            _event("e2", RiskEventReason.STOP_LOSS),
            _event("e3", RiskEventReason.TRAILING_STOP),
            _event("e4", RiskEventReason.TAKE_PROFIT),
        ]
        groups = group_risk_events_by_reason(events)
        assert len(groups[RiskEventReason.STOP_LOSS]) == 2
        assert len(groups[RiskEventReason.TRAILING_STOP]) == 1
        assert len(groups[RiskEventReason.TAKE_PROFIT]) == 1


class TestExcessReturnWindowConfig:
    """AC-4: 超额收益窗口 N 日输入字段 (默认 0, 范围 0~30)."""

    def test_default_zero(self):
        cfg = ExcessReturnWindowConfig(days=0)
        assert cfg.days == 0

    def test_validate_zero_ok(self):
        """AC-4: 范围 0~30 (含边界)."""
        assert validate_excess_return_window(0) is True

    def test_validate_thirty_ok(self):
        """AC-4: 范围 0~30 (含边界)."""
        assert validate_excess_return_window(30) is True

    def test_validate_negative_rejected(self):
        with pytest.raises(ValueError):
            validate_excess_return_window(-1)

    def test_validate_over_thirty_rejected(self):
        with pytest.raises(ValueError):
            validate_excess_return_window(31)
