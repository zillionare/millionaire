"""ErrorEnvelope 与业务错误码单元测试 (interfaces.md §1).

覆盖 ErrorEnvelope schema 与业务错误码 HTTP 映射.
"""
from __future__ import annotations

import pytest

from quantide.web.errors import (
    ERROR_CODE_HTTP_STATUS,
    ErrorCode,
    ErrorEnvelope,
    build_error_envelope,
)


class TestErrorCodeHttpStatus:
    """interfaces.md §1.2 业务错误码 HTTP 映射."""

    @pytest.mark.parametrize(
        "code,expected_http",
        [
            (ErrorCode.AUTH_REQUIRED, 401),
            (ErrorCode.NOT_INITIALIZED, 303),
            (ErrorCode.VALIDATION_ERROR, 400),
            (ErrorCode.GATEWAY_NOT_CONFIGURED, 503),
            (ErrorCode.GATEWAY_OFFLINE, 503),
            (ErrorCode.BROKER_RUNTIME_ERROR, 502),
            (ErrorCode.DATA_SOURCE_UNAVAILABLE, 503),
            (ErrorCode.TASK_RUNNING, 409),
            (ErrorCode.NOT_FOUND, 404),
            (ErrorCode.INTERNAL_ERROR, 500),
        ],
    )
    def test_http_status_mapping(self, code, expected_http):
        assert ERROR_CODE_HTTP_STATUS[code] == expected_http


class TestErrorEnvelope:
    """interfaces.md §1.1 ErrorEnvelope schema."""

    def test_required_fields(self):
        env = ErrorEnvelope(
            ok=False,
            code=ErrorCode.VALIDATION_ERROR,
            message="字段错误",
        )
        assert env.ok is False
        assert env.code == ErrorCode.VALIDATION_ERROR
        assert env.message == "字段错误"

    def test_optional_fields_default_none(self):
        env = ErrorEnvelope(ok=False, code=ErrorCode.NOT_FOUND, message="不存在")
        assert env.details is None
        assert env.retry_after_seconds is None
        assert env.request_id is None

    def test_details_not_leak_sensitive(self):
        """details 不含 token/password (interfaces.md §1.1)."""
        env = ErrorEnvelope(
            ok=False,
            code=ErrorCode.VALIDATION_ERROR,
            message="字段错误",
            details={"field": "username", "reason": "required"},
        )
        assert "password" not in str(env.details).lower()
        assert "token" not in str(env.details).lower()


class TestBuildErrorEnvelope:
    def test_build_validation_error(self):
        env = build_error_envelope(
            ErrorCode.VALIDATION_ERROR,
            "本金必须 > 0",
            details={"field": "principal"},
        )
        assert env.ok is False
        assert env.code == ErrorCode.VALIDATION_ERROR
        assert env.details == {"field": "principal"}

    def test_build_gateway_offline_with_retry(self):
        env = build_error_envelope(
            ErrorCode.GATEWAY_OFFLINE,
            "网关离线",
            retry_after_seconds=30,
        )
        assert env.retry_after_seconds == 30
