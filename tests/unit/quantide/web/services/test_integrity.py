"""FR-0320 数据完整性校验报告单元测试.

覆盖 acceptance.md AC-FR0320-1:
- 缺日列表
- 重复日列表
- 字段空值率 (超过阈值 5% 标红)
- 校验历史 (最近 N=10 次)
"""
from __future__ import annotations

import pytest

from quantide.web.services.integrity import (
    DEFAULT_NULL_RATE_THRESHOLD,
    FieldNullRate,
    IntegrityHistoryItem,
    IntegrityReport,
    IntegrityStatus,
    is_field_over_threshold,
    truncate_integrity_history,
)


class TestIntegrityReport:
    """AC-1: 校验报告字段."""

    def test_report_has_all_sections(self):
        report = IntegrityReport(
            missing_days=["2024-01-15"],
            duplicate_days=["2024-02-20"],
            field_null_rates=[FieldNullRate(field="close", null_rate=0.02)],
        )
        assert report.missing_days == ["2024-01-15"]
        assert report.duplicate_days == ["2024-02-20"]
        assert len(report.field_null_rates) == 1

    def test_empty_report(self):
        report = IntegrityReport(missing_days=[], duplicate_days=[], field_null_rates=[])
        assert report.missing_days == []


class TestNullRateThreshold:
    """AC-1: 字段空值率超过阈值 (例如 5%) 标红."""

    def test_default_threshold_is_five_percent(self):
        assert DEFAULT_NULL_RATE_THRESHOLD == 0.05

    def test_field_over_threshold_flagged(self):
        """AC-1: 超过阈值标红."""
        field = FieldNullRate(field="close", null_rate=0.08)
        assert is_field_over_threshold(field) is True

    def test_field_at_threshold_not_flagged(self):
        field = FieldNullRate(field="close", null_rate=0.05)
        assert is_field_over_threshold(field) is False

    def test_field_under_threshold_not_flagged(self):
        field = FieldNullRate(field="close", null_rate=0.02)
        assert is_field_over_threshold(field) is False


class TestIntegrityHistory:
    """AC-1: 校验历史最近 N=10 次."""

    def test_truncate_to_ten(self):
        history = [
            IntegrityHistoryItem(
                checked_at=f"2026-07-09T1{i}:00:00",
                status=IntegrityStatus.PASSED,
                failure_reason=None,
            )
            for i in range(15)
        ]
        truncated = truncate_integrity_history(history)
        assert len(truncated) == 10
