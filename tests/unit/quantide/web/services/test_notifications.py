"""FR-0450 通知配置界面单元测试.

覆盖 acceptance.md AC-FR0450-1~5:
- 微信二维码启用 (AC-1, AC-2)
- 订阅事件类型: 委托/成交/失败/网关断开 (AC-3)
- 无静默时段配置项 (AC-4)
- IM / 邮件渠道配置 (AC-5)
"""
from __future__ import annotations

import pytest

from quantide.web.services.notifications import (
    NOTIFICATION_CHANNELS,
    NotificationChannel,
    NotificationSubscription,
    NotificationSubscriptionError,
    SUBSCRIBABLE_EVENT_TYPES,
    SUPPORTS_SILENT_PERIOD,
    WechatBindingState,
    validate_subscription,
)


class TestNotificationChannels:
    """AC-5: IM / 邮件渠道."""

    def test_has_three_channels(self):
        assert NotificationChannel.WECHAT in NOTIFICATION_CHANNELS
        assert NotificationChannel.IM in NOTIFICATION_CHANNELS
        assert NotificationChannel.EMAIL in NOTIFICATION_CHANNELS


class TestSubscribableEventTypes:
    """AC-3: 订阅事件类型 委托/成交/失败/网关断开."""

    def test_has_four_event_types(self):
        assert "order" in SUBSCRIBABLE_EVENT_TYPES
        assert "trade" in SUBSCRIBABLE_EVENT_TYPES
        assert "failure" in SUBSCRIBABLE_EVENT_TYPES
        assert "gateway_offline" in SUBSCRIBABLE_EVENT_TYPES


class TestNoSilentPeriod:
    """AC-4: 无静默时段配置项 (Aaron 决策)."""

    def test_silent_period_not_supported(self):
        assert SUPPORTS_SILENT_PERIOD is False


class TestWechatBinding:
    """AC-1, AC-2: 微信二维码启用."""

    def test_initial_state_pending(self):
        state = WechatBindingState(bound=False, qr_token="abc123", status="pending")
        assert state.bound is False
        assert state.qr_token == "abc123"

    def test_bound_state(self):
        state = WechatBindingState(bound=True, qr_token=None, status="bound")
        assert state.bound is True


class TestSubscriptionValidation:
    """AC-3: 订阅校验."""

    def test_valid_wechat_subscription(self):
        sub = NotificationSubscription(
            channel=NotificationChannel.WECHAT,
            enabled=True,
            receiver=None,
            event_types=["order", "trade"],
        )
        assert validate_subscription(sub) is True

    def test_wechat_does_not_require_receiver(self):
        sub = NotificationSubscription(
            channel=NotificationChannel.WECHAT,
            enabled=True,
            receiver=None,
            event_types=["order"],
        )
        assert validate_subscription(sub) is True

    def test_im_requires_receiver(self):
        sub = NotificationSubscription(
            channel=NotificationChannel.IM,
            enabled=True,
            receiver="",
            event_types=["order"],
        )
        with pytest.raises(NotificationSubscriptionError) as exc:
            validate_subscription(sub)
        assert "接收方" in str(exc.value)

    def test_email_requires_receiver(self):
        """AC-5: 邮件配置输入接收方."""
        sub = NotificationSubscription(
            channel=NotificationChannel.EMAIL,
            enabled=True,
            receiver="",
            event_types=["order"],
        )
        with pytest.raises(NotificationSubscriptionError):
            validate_subscription(sub)

    def test_invalid_event_type_rejected(self):
        sub = NotificationSubscription(
            channel=NotificationChannel.WECHAT,
            enabled=True,
            receiver=None,
            event_types=["unknown_event"],
        )
        with pytest.raises(NotificationSubscriptionError):
            validate_subscription(sub)

    def test_disabled_subscription_skips_receiver_check(self):
        """禁用的渠道不需要接收方."""
        sub = NotificationSubscription(
            channel=NotificationChannel.IM,
            enabled=False,
            receiver="",
            event_types=[],
        )
        assert validate_subscription(sub) is True
