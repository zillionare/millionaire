"""FR-450 通知事件枚举."""

from __future__ import annotations

from enum import Enum


class NotificationEvent(str, Enum):
    """通知事件定义 (FR-450).

    通知触发事件 (若用户已启用微信通知):
    - 委托提交 (ORDER_SUBMITTED)
    - 成交 (TRADE_FILLED)
    - 委托失败 (ORDER_FAILED)
    - 成交失败 (TRADE_FAILED)
    - 实盘交易网关断开 (GATEWAY_DISCONNECTED)

    通知配置 UI 已迁移到 v0.2-002-ui/spec.md UI-FR-450.
    本枚举仅定义事件, 实际通知发送留给 UI 层.
    """

    ORDER_SUBMITTED = "order_submitted"
    TRADE_FILLED = "trade_filled"
    ORDER_FAILED = "order_failed"
    TRADE_FAILED = "trade_failed"
    GATEWAY_DISCONNECTED = "gateway_disconnected"