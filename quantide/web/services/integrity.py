"""FR-0320 数据完整性校验报告服务.

定义校验报告 schema (缺日/重复日/字段空值率/校验历史) 与阈值标红规则.

AC-1: 字段空值率超过阈值 (例如 5%) 标红; 校验历史最近 N=10 次.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEFAULT_NULL_RATE_THRESHOLD: float = 0.05
_INTEGRITY_HISTORY_LIMIT = 10


class IntegrityStatus(str, Enum):
    """校验状态."""

    PASSED = "passed"
    FAILED = "failed"


@dataclass
class FieldNullRate:
    """字段空值率.

    Attributes:
        field: 字段名.
        null_rate: 空值百分比 (0~1).
    """

    field: str
    null_rate: float


@dataclass
class IntegrityHistoryItem:
    """校验历史条目.

    Attributes:
        checked_at: 校验时间.
        status: 校验状态.
        failure_reason: 失败原因 (通过时为 None).
    """

    checked_at: str
    status: IntegrityStatus
    failure_reason: str | None


@dataclass
class IntegrityReport:
    """完整性校验报告 (AC-FR0320-1).

    Attributes:
        missing_days: 缺日列表.
        duplicate_days: 重复日列表.
        field_null_rates: 各字段空值率.
    """

    missing_days: list[str]
    duplicate_days: list[str]
    field_null_rates: list[FieldNullRate]


def is_field_over_threshold(
    field: FieldNullRate,
    threshold: float = DEFAULT_NULL_RATE_THRESHOLD,
) -> bool:
    """AC-1: 判断字段空值率是否超过阈值 (标红).

    Args:
        field: 字段空值率.
        threshold: 阈值 (默认 5%).

    Returns:
        True 当空值率超过阈值.
    """
    return field.null_rate > threshold


def truncate_integrity_history(
    history: list[IntegrityHistoryItem],
) -> list[IntegrityHistoryItem]:
    """AC-1: 截断校验历史到最近 N=10 次.

    Args:
        history: 完整历史.

    Returns:
        最近 10 条历史.
    """
    return history[-_INTEGRITY_HISTORY_LIMIT:]


__all__ = [
    "DEFAULT_NULL_RATE_THRESHOLD",
    "FieldNullRate",
    "IntegrityHistoryItem",
    "IntegrityReport",
    "IntegrityStatus",
    "is_field_over_threshold",
    "truncate_integrity_history",
]
