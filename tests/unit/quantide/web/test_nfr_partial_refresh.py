"""NFR-0050 局部刷新与失败隔离单元测试.

覆盖 acceptance.md AC-NFR0050-1~3:
- 局部数据失败不能导致整页失效 (失败区域占位 + 重试按钮)
- 局部刷新不得造成整页跳动或闪屏 (布局稳定)
- 失败区域独立重试
"""
from __future__ import annotations

import pytest

from quantide.web.nfr_partial_refresh import (
    assert_no_layout_shift,
    independent_region_id,
    partial_failure_placeholder,
    retry_region_payload,
)


class TestPartialFailurePlaceholder:
    """AC-NFR0050-1: 局部失败占位."""

    def test_placeholder_has_error_icon(self):
        placeholder = partial_failure_placeholder("orders")
        assert "error" in placeholder["icon"].lower()

    def test_placeholder_has_failure_text(self):
        placeholder = partial_failure_placeholder("orders")
        assert "加载失败" in placeholder["message"]

    def test_placeholder_has_retry_button(self):
        placeholder = partial_failure_placeholder("orders")
        assert placeholder["retry_button"] is True


class TestRetryRegionPayload:
    """AC-NFR0050-3: 失败区域独立重试."""

    def test_payload_targets_region(self):
        payload = retry_region_payload("orders", "/api/orders")
        assert payload["target"] == "orders"
        assert payload["url"] == "/api/orders"


class TestLayoutShift:
    """AC-NFR0050-2: 局部刷新不得造成整页跳动."""

    def test_same_rect_no_shift(self):
        rect = {"x": 0, "y": 100, "width": 800, "height": 200}
        assert assert_no_layout_shift(rect, rect) is True

    def test_small_change_within_tolerance(self):
        old = {"x": 0, "y": 100, "width": 800, "height": 200}
        new = {"x": 0, "y": 101, "width": 800, "height": 200}
        assert assert_no_layout_shift(old, new) is True

    def test_large_change_detected_as_shift(self):
        old = {"x": 0, "y": 100, "width": 800, "height": 200}
        new = {"x": 0, "y": 150, "width": 800, "height": 200}
        assert assert_no_layout_shift(old, new) is False


class TestIndependentRegionId:
    def test_region_id_is_stable(self):
        assert independent_region_id("trade", "orders") == independent_region_id("trade", "orders")

    def test_region_id_differs_by_region(self):
        assert independent_region_id("trade", "orders") != independent_region_id("trade", "trades")
