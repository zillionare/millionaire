"""PushEvent schema (interfaces.md §4.5).

定义 SSE 推送事件类型与 payload 必备字段校验.
/events/stream 端点向浏览器推送 alert/order/portfolio/task_progress/gateway_status.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PushEventType(str, Enum):
    """推送事件类型 (interfaces.md §4.5)."""

    ALERT = "alert"
    ORDER = "order"
    PORTFOLIO = "portfolio"
    TASK_PROGRESS = "task_progress"
    GATEWAY_STATUS = "gateway_status"


@dataclass
class PushEvent:
    """推送事件 (interfaces.md §4.5).

    Attributes:
        event_id: 单调/唯一, 用于断线续传.
        type: 事件类型.
        created_at: ISO datetime.
        payload: 按事件类型变化.
    """

    event_id: str
    type: PushEventType
    created_at: str
    payload: dict[str, Any]


_REQUIRED_ALERT_FIELDS = {"alert_id", "unread_count"}
_REQUIRED_ORDER_FIELDS = {"order_id", "strategy_id", "status", "message"}
_REQUIRED_PORTFOLIO_FIELDS = {"account_id", "total_assets", "available_cash", "market_value", "daily_pnl"}
_REQUIRED_TASK_PROGRESS_FIELDS = {"task_id", "task_name", "percent", "stage", "status", "message"}
_REQUIRED_GATEWAY_STATUS_FIELDS = {"status", "degrade_class", "message"}
_VALID_GATEWAY_STATUSES = {"online", "offline", "not_configured"}
_VALID_DEGRADE_CLASSES = {"A", "B", None}


def _has_required(payload: dict[str, Any], required: set[str]) -> bool:
    return required.issubset(payload.keys())


def validate_alert_payload(payload: dict[str, Any]) -> bool:
    """校验 alert payload 必备字段.

    Args:
        payload: 事件 payload.

    Returns:
        True 当包含 alert_id 与 unread_count.
    """
    return _has_required(payload, _REQUIRED_ALERT_FIELDS)


def validate_order_payload(payload: dict[str, Any]) -> bool:
    """校验 order payload 必备字段.

    Args:
        payload: 事件 payload.

    Returns:
        True 当包含 order_id / strategy_id / status / message.
    """
    return _has_required(payload, _REQUIRED_ORDER_FIELDS)


def validate_portfolio_payload(payload: dict[str, Any]) -> bool:
    """校验 portfolio payload 必备字段.

    Args:
        payload: 事件 payload.

    Returns:
        True 当包含 account_id / total_assets / available_cash / market_value / daily_pnl.
    """
    return _has_required(payload, _REQUIRED_PORTFOLIO_FIELDS)


def validate_task_progress_payload(payload: dict[str, Any]) -> bool:
    """校验 task_progress payload 必备字段.

    Args:
        payload: 事件 payload.

    Returns:
        True 当包含 task_id / task_name / percent / stage / status / message.
    """
    return _has_required(payload, _REQUIRED_TASK_PROGRESS_FIELDS)


def validate_gateway_status_payload(payload: dict[str, Any]) -> bool:
    """校验 gateway_status payload 必备字段与枚举值.

    Args:
        payload: 事件 payload.

    Returns:
        True 当 status 为 online/offline/not_configured 且 degrade_class 为 A/B/null.
    """
    if not _has_required(payload, _REQUIRED_GATEWAY_STATUS_FIELDS):
        return False
    status = payload.get("status")
    if status not in _VALID_GATEWAY_STATUSES:
        return False
    degrade_class = payload.get("degrade_class")
    return degrade_class in _VALID_DEGRADE_CLASSES


__all__ = [
    "PushEvent",
    "PushEventType",
    "validate_alert_payload",
    "validate_gateway_status_payload",
    "validate_order_payload",
    "validate_portfolio_payload",
    "validate_task_progress_payload",
]
