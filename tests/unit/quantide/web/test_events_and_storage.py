"""PushEvent schema 与 localStorage key 契约单元测试.

覆盖:
- interfaces.md §4.5 PushEvent schema (5 种 type + payload 必备字段)
- interfaces.md §6 localStorage key 契约 (白名单 + 禁止敏感信息)
- NFR-0070 AC-5: localStorage 不存储密码/session token
"""
from __future__ import annotations

import pytest

from quantide.web.events import (
    PushEvent,
    PushEventType,
    validate_alert_payload,
    validate_gateway_status_payload,
    validate_order_payload,
    validate_portfolio_payload,
    validate_task_progress_payload,
)
from quantide.web.local_storage import (
    FORBIDDEN_KEYS,
    LOCAL_STORAGE_KEYS,
    is_sensitive_key,
    is_valid_local_storage_key,
)


class TestPushEventType:
    def test_has_five_types(self):
        assert PushEventType.ALERT == "alert"
        assert PushEventType.ORDER == "order"
        assert PushEventType.PORTFOLIO == "portfolio"
        assert PushEventType.TASK_PROGRESS == "task_progress"
        assert PushEventType.GATEWAY_STATUS == "gateway_status"


class TestAlertPayload:
    """interfaces.md §4.5 alert payload 必备字段."""

    def test_valid_alert_payload(self):
        payload = {
            "alert_id": "a1",
            "created_at": "2026-07-09T10:00:00",
            "source": "system",
            "category": "system",
            "level": "error",
            "summary": "fail",
            "detail_url": "/alert/a1",
            "read": False,
            "confirmed": False,
            "unread_count": 3,
        }
        assert validate_alert_payload(payload) is True

    def test_missing_unread_count_invalid(self):
        payload = {"alert_id": "a1", "unread_count": 0}
        payload.pop("unread_count", None)
        assert validate_alert_payload(payload) is False


class TestOrderPayload:
    def test_valid_order_payload(self):
        payload = {"order_id": "o1", "strategy_id": "s1", "status": "submitted", "message": "ok"}
        assert validate_order_payload(payload) is True

    def test_missing_order_id_invalid(self):
        assert validate_order_payload({"strategy_id": "s1"}) is False


class TestPortfolioPayload:
    def test_valid(self):
        payload = {"account_id": "a1", "total_assets": 100000, "available_cash": 50000, "market_value": 50000, "daily_pnl": 1000}
        assert validate_portfolio_payload(payload) is True


class TestTaskProgressPayload:
    def test_valid(self):
        payload = {"task_id": "t1", "task_name": "日线", "percent": 60, "stage": "downloading", "status": "running", "message": "ok"}
        assert validate_task_progress_payload(payload) is True


class TestGatewayStatusPayload:
    """interfaces.md §4.5 gateway_status payload."""

    def test_valid_online(self):
        payload = {"status": "online", "degrade_class": None, "message": "ok"}
        assert validate_gateway_status_payload(payload) is True

    def test_valid_offline_class_b(self):
        payload = {"status": "offline", "degrade_class": "B", "message": "断开"}
        assert validate_gateway_status_payload(payload) is True

    def test_valid_not_configured_class_a(self):
        payload = {"status": "not_configured", "degrade_class": "A", "message": "未配置"}
        assert validate_gateway_status_payload(payload) is True

    def test_invalid_status_value(self):
        assert validate_gateway_status_payload({"status": "unknown"}) is False


class TestPushEventModel:
    def test_event_carries_event_id_and_type(self):
        event = PushEvent(event_id="e1", type=PushEventType.ALERT, created_at="2026-07-09T10:00:00", payload={"unread_count": 0})
        assert event.event_id == "e1"
        assert event.type == PushEventType.ALERT


class TestLocalStorageWhitelist:
    """interfaces.md §6 localStorage key 契约."""

    def test_allowed_keys_present(self):
        assert "quantide.sidebar.collapsed" in LOCAL_STORAGE_KEYS
        assert "quantide.accounts.display_hidden" in LOCAL_STORAGE_KEYS
        assert "quantide.runtime_params.last" in LOCAL_STORAGE_KEYS
        assert "quantide.filters.strategy" in LOCAL_STORAGE_KEYS
        assert "quantide.wizard.pending_banner.dismissed_at" in LOCAL_STORAGE_KEYS

    def test_valid_key_accepted(self):
        assert is_valid_local_storage_key("quantide.sidebar.collapsed") is True

    def test_unknown_key_rejected(self):
        assert is_valid_local_storage_key("quantide.unknown.key") is False


class TestForbiddenSensitiveKeys:
    """NFR-0070 AC-5: localStorage 不存储敏感信息."""

    @pytest.mark.parametrize(
        "key",
        ["password", "session_token", "tushare_token", "qmt_gateway_api_key", "api_key", "secret"],
    )
    def test_sensitive_keys_detected(self, key):
        """禁止 key: password, session token, Tushare token, qmt-gateway api_key (interfaces.md §6)."""
        assert is_sensitive_key(key) is True

    def test_forbidden_keys_set_includes_sensitive(self):
        assert "password" in FORBIDDEN_KEYS
        assert "session_token" in FORBIDDEN_KEYS
