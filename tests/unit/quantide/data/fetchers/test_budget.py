"""Data-source budget and error taxonomy contracts."""

import pytest

from quantide.data.fetchers.budget import (
    BudgetDecision,
    DataSourceErrorKind,
    NoQuotaBudget,
    budget_for_fetcher,
    classify_source_error,
    retryable,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("今日调用次数已用完", DataSourceErrorKind.QUOTA_EXHAUSTED),
        ("抱歉，您每分钟最多访问该接口 500 次", DataSourceErrorKind.RATE_LIMITED),
        ("token无效", DataSourceErrorKind.AUTH_ERROR),
        ("账号缺少此接口权限", DataSourceErrorKind.PERMISSION_DENIED),
        ("403 Client Error: Forbidden", DataSourceErrorKind.PERMISSION_DENIED),
        ("429 Too Many Requests", DataSourceErrorKind.RATE_LIMITED),
        ("连接超时", DataSourceErrorKind.TRANSIENT),
        ("返回空数据", DataSourceErrorKind.EMPTY_DATA),
        ("参数错误", DataSourceErrorKind.INVALID_REQUEST),
        ("something odd happened", DataSourceErrorKind.UNKNOWN),
    ],
)
def test_classify_source_error(message: str, expected: DataSourceErrorKind) -> None:
    assert classify_source_error(message) is expected


def test_no_quota_budget_never_fakes_exhaustion() -> None:
    budget = NoQuotaBudget("tencent")

    assert budget.snapshot() is None
    assert budget.acquire() is BudgetDecision.UNKNOWN
    assert budget.requests_seen == 1
    assert budget.classify("timeout") is DataSourceErrorKind.TRANSIENT


def test_retryability_is_explicit() -> None:
    assert retryable(DataSourceErrorKind.QUOTA_EXHAUSTED)
    assert retryable(DataSourceErrorKind.RATE_LIMITED)
    assert not retryable(DataSourceErrorKind.PERMISSION_DENIED)
    assert not retryable(DataSourceErrorKind.EMPTY_DATA)


def test_budget_for_fetcher_uses_declared_budget() -> None:
    declared = NoQuotaBudget("custom")

    class _Fetcher:
        source_name = "custom"

        def budget(self):
            return declared

    assert budget_for_fetcher(_Fetcher()) is declared


def test_budget_for_fetcher_falls_back_without_faking_quota() -> None:
    class _Fetcher:
        source_name = "scraper"

    budget = budget_for_fetcher(_Fetcher())

    assert isinstance(budget, NoQuotaBudget)
    assert budget.snapshot() is None
