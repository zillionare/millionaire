"""ErrorEnvelope 与业务错误码 (interfaces.md §1).

定义统一的错误响应 schema 与业务错误码到 HTTP 状态码的映射.
所有 UI 出口错误均通过 ErrorEnvelope 观察, details 不含敏感信息 (token/password).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """业务错误码 (interfaces.md §1.2)."""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    NOT_INITIALIZED = "NOT_INITIALIZED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    GATEWAY_NOT_CONFIGURED = "GATEWAY_NOT_CONFIGURED"
    GATEWAY_OFFLINE = "GATEWAY_OFFLINE"
    BROKER_RUNTIME_ERROR = "BROKER_RUNTIME_ERROR"
    DATA_SOURCE_UNAVAILABLE = "DATA_SOURCE_UNAVAILABLE"
    TASK_RUNNING = "TASK_RUNNING"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_CODE_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.AUTH_REQUIRED: 401,
    ErrorCode.NOT_INITIALIZED: 303,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.GATEWAY_NOT_CONFIGURED: 503,
    ErrorCode.GATEWAY_OFFLINE: 503,
    ErrorCode.BROKER_RUNTIME_ERROR: 502,
    ErrorCode.DATA_SOURCE_UNAVAILABLE: 503,
    ErrorCode.TASK_RUNNING: 409,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.INTERNAL_ERROR: 500,
}


@dataclass
class ErrorEnvelope:
    """统一错误响应 (interfaces.md §1.1).

    Attributes:
        ok: 固定 False.
        code: 业务错误码.
        message: 用户可见中文消息.
        details: 字段错误/诊断信息, 不含 token/password.
        retry_after_seconds: 自动重试倒计时.
        request_id: 排查用请求 ID.
    """

    ok: bool
    code: ErrorCode
    message: str
    details: dict | None = None
    retry_after_seconds: int | None = None
    request_id: str | None = None


def build_error_envelope(
    code: ErrorCode,
    message: str,
    *,
    details: dict | None = None,
    retry_after_seconds: int | None = None,
    request_id: str | None = None,
) -> ErrorEnvelope:
    """构建 ErrorEnvelope.

    Args:
        code: 业务错误码.
        message: 用户可见消息.
        details: 字段错误/诊断信息 (调用方负责不含敏感信息).
        retry_after_seconds: 自动重试倒计时.
        request_id: 排查用请求 ID.

    Returns:
        ErrorEnvelope 实例.
    """
    return ErrorEnvelope(
        ok=False,
        code=code,
        message=message,
        details=details,
        retry_after_seconds=retry_after_seconds,
        request_id=request_id,
    )


__all__ = [
    "ERROR_CODE_HTTP_STATUS",
    "ErrorCode",
    "ErrorEnvelope",
    "build_error_envelope",
]
