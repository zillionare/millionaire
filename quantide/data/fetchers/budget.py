"""Data-source request budgets and error classification.

Quota support is deliberately optional.  A source without a native quota must
still expose a budget implementation so callers have one scheduling contract,
but the implementation should report ``UNKNOWN`` instead of pretending that
every failure is a quota exhaustion.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast


class DataSourceErrorKind(StrEnum):
    """Stable failure classes shared by backfill scheduling and alerting."""

    QUOTA_EXHAUSTED = "quota_exhausted"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    PERMISSION_DENIED = "permission_denied"
    TRANSIENT = "transient"
    INVALID_REQUEST = "invalid_request"
    EMPTY_DATA = "empty_data"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class QuotaSnapshot:
    """A source-reported or locally estimated quota state."""

    source: str
    limit: int | None = None
    used: int | None = None
    remaining: int | None = None
    reset_at: datetime.datetime | None = None
    unit: str = "request"


class BudgetDecision(StrEnum):
    """Scheduler decision before issuing one request or batch."""

    ALLOW = "allow"
    DELAY = "delay"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"


class DataSourceBudget(Protocol):
    """Required scheduling interface for every historical data adapter."""

    source: str

    def snapshot(self) -> QuotaSnapshot | None:
        """Return native quota information when the source exposes it."""
        ...

    def acquire(self, cost: int = 1) -> BudgetDecision:
        """Reserve budget before a request; never refund a crashed reservation."""
        ...

    def observe(self, error: BaseException | None = None) -> None:
        """Update local accounting after a request completes."""
        ...

    def classify(self, error: BaseException | str) -> DataSourceErrorKind:
        """Map a source response to the shared error taxonomy."""
        ...


_QUOTA_WORDS = (
    "额度不足",
    "额度已用尽",
    "quota exceeded",
    "quota exhausted",
    "daily limit",
    "今日调用次数",
    "超过每日",
    "次数已用完",
)
_RATE_WORDS = (
    "频率",
    "频次",
    "限流",
    "最多访问",
    "rate limit",
    "too many",
    "429",
)
_AUTH_WORDS = (
    "token不对",
    "token无效",
    "invalid token",
    "token过期",
    "unauthorized",
    "401",
)
_PERMISSION_WORDS = (
    "权限",
    "积分",
    "permission",
    "not authorized",
    "无权",
    "forbidden",
)
_TRANSIENT_WORDS = (
    "timeout",
    "timed out",
    "超时",
    "connection",
    "连接失败",
    "network",
    "网络",
    "502",
    "503",
    "504",
    "temporarily",
    "不可用",
)
_EMPTY_WORDS = ("无数据", "没有数据", "no data", "empty", "返回空")


def classify_source_error(error: BaseException | str) -> DataSourceErrorKind:
    """Classify without turning unrelated failures into quota exhaustion."""
    if isinstance(error, (TimeoutError, ConnectionError)):
        return DataSourceErrorKind.TRANSIENT
    text = str(error).casefold()
    if any(word in text for word in _QUOTA_WORDS):
        return DataSourceErrorKind.QUOTA_EXHAUSTED
    if any(word in text for word in _RATE_WORDS):
        return DataSourceErrorKind.RATE_LIMITED
    if any(word in text for word in _AUTH_WORDS):
        return DataSourceErrorKind.AUTH_ERROR
    if any(word in text for word in _PERMISSION_WORDS):
        return DataSourceErrorKind.PERMISSION_DENIED
    if any(word in text for word in _TRANSIENT_WORDS):
        return DataSourceErrorKind.TRANSIENT
    if any(word in text for word in _EMPTY_WORDS):
        return DataSourceErrorKind.EMPTY_DATA
    if any(word in text for word in ("invalid", "参数", "字段")):
        return DataSourceErrorKind.INVALID_REQUEST
    return DataSourceErrorKind.UNKNOWN


def retryable(kind: DataSourceErrorKind) -> bool:
    """Return whether the same gap should be retried automatically."""
    return kind in {
        DataSourceErrorKind.QUOTA_EXHAUSTED,
        DataSourceErrorKind.RATE_LIMITED,
        DataSourceErrorKind.TRANSIENT,
        DataSourceErrorKind.UNKNOWN,
    }


def budget_for_fetcher(fetcher: object) -> DataSourceBudget:
    """Read an adapter budget or fall back to an explicit unknown-quota policy."""
    factory = getattr(fetcher, "budget", None)
    if callable(factory):
        budget = cast(DataSourceBudget | None, factory())
        if budget is not None:
            return budget
    source = str(getattr(fetcher, "source_name", "") or "unknown")
    return NoQuotaBudget(source)


@dataclass
class NoQuotaBudget:
    """Default implementation for sources without a queryable quota."""

    source: str
    requests_seen: int = 0

    def snapshot(self) -> QuotaSnapshot | None:
        return None

    def acquire(self, cost: int = 1) -> BudgetDecision:
        self.requests_seen += max(0, int(cost))
        return BudgetDecision.UNKNOWN

    def observe(self, error: BaseException | None = None) -> None:
        _ = error

    def classify(self, error: BaseException | str) -> DataSourceErrorKind:
        return classify_source_error(error)


__all__ = [
    "BudgetDecision",
    "DataSourceBudget",
    "DataSourceErrorKind",
    "NoQuotaBudget",
    "QuotaSnapshot",
    "budget_for_fetcher",
    "classify_source_error",
    "retryable",
]
