"""NFR-0010 响应性单元测试.

覆盖 acceptance.md AC-NFR0010-1~3:
- 冷启动首屏渲染 LCP < 2s
- 委托/成交列表实时刷新延迟 < 5s
- 10000 行表格滚动 FPS >= 30
"""
from __future__ import annotations

import pytest

from quantide.web.nfr_responsive import (
    LCP_BUDGET_MS,
    REFRESH_LATENCY_BUDGET_S,
    SCROLL_FPS_BUDGET,
    is_lcp_acceptable,
    is_refresh_latency_acceptable,
    is_scroll_fps_acceptable,
)


class TestLCPBudget:
    """AC-NFR0010-1: 冷启动首屏渲染 LCP < 2s."""

    def test_lcp_under_budget_acceptable(self):
        assert is_lcp_acceptable(1500) is True

    def test_lcp_at_budget_not_acceptable(self):
        assert is_lcp_acceptable(2000) is False

    def test_lcp_over_budget_not_acceptable(self):
        assert is_lcp_acceptable(2500) is False


class TestRefreshLatencyBudget:
    """AC-NFR0010-2: 委托/成交列表实时刷新延迟 < 5s."""

    def test_latency_under_budget_acceptable(self):
        assert is_refresh_latency_acceptable(3.5) is True

    def test_latency_at_budget_not_acceptable(self):
        assert is_refresh_latency_acceptable(5.0) is False

    def test_latency_over_budget_not_acceptable(self):
        assert is_refresh_latency_acceptable(6.0) is False


class TestScrollFPSBudget:
    """AC-NFR0010-3: 表格滚动 FPS >= 30."""

    def test_fps_at_budget_acceptable(self):
        assert is_scroll_fps_acceptable(30) is True

    def test_fps_above_budget_acceptable(self):
        assert is_scroll_fps_acceptable(60) is True

    def test_fps_below_budget_not_acceptable(self):
        assert is_scroll_fps_acceptable(20) is False
