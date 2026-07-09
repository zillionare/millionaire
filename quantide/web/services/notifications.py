"""FR-0450 通知配置界面服务.

定义通知渠道 (微信/IM/邮件)、订阅事件类型与校验规则.

AC-3: 订阅事件类型 委托/成交/失败/网关断开.
AC-4: 无静默时段配置项 (Aaron 决策: 不需要静默时段).
AC-5: IM / 邮件渠道需输入接收方.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NotificationChannel(str, Enum):
    """通知渠道."""

    WECHAT = "wechat"
    IM = "im"
    EMAIL = "email"


NOTIFICATION_CHANNELS: tuple[NotificationChannel, ...] = (
    NotificationChannel.WECHAT,
    NotificationChannel.IM,
    NotificationChannel.EMAIL,
)

SUBSCRIBABLE_EVENT_TYPES: frozenset[str] = frozenset(
    {"order", "trade", "failure", "gateway_offline"}
)

SUPPORTS_SILENT_PERIOD: bool = False


@dataclass
class WechatBindingState:
    """AC-1, AC-2: 微信二维码绑定状态.

    Attributes:
        bound: 是否已绑定.
        qr_token: 一次性二维码 token (未绑定时生成).
        status: pending / bound / failed.
    """

    bound: bool
    qr_token: str | None
    status: str


@dataclass
class NotificationSubscription:
    """通知订阅配置 (interfaces.md §4.7).

    Attributes:
        channel: 通知渠道.
        enabled: 是否启用.
        receiver: IM/email 接收方 (微信可为 None).
        event_types: 订阅事件类型集合.
    """

    channel: NotificationChannel
    enabled: bool
    receiver: str | None
    event_types: list[str]


class NotificationSubscriptionError(ValueError):
    """通知订阅校验错误."""


def validate_subscription(sub: NotificationSubscription) -> bool:
    """AC-3, AC-5: 校验订阅配置.

    Args:
        sub: 订阅配置.

    Returns:
        True 当配置合法.

    Raises:
        NotificationSubscriptionError: 当渠道为 IM/email 且未填接收方, 或事件类型非法.
    """
    if not sub.enabled:
        return True
    if sub.channel in (NotificationChannel.IM, NotificationChannel.EMAIL):
        if not sub.receiver or not str(sub.receiver).strip():
            raise NotificationSubscriptionError(f"{sub.channel.value} 渠道必须填写接收方")
    for event_type in sub.event_types:
        if event_type not in SUBSCRIBABLE_EVENT_TYPES:
            raise NotificationSubscriptionError(f"不支持的事件类型: {event_type}")
    return True


__all__ = [
    "NOTIFICATION_CHANNELS",
    "NotificationChannel",
    "NotificationSubscription",
    "NotificationSubscriptionError",
    "SUBSCRIBABLE_EVENT_TYPES",
    "SUPPORTS_SILENT_PERIOD",
    "WechatBindingState",
    "validate_subscription",
]
