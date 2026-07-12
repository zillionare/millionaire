"""NFR-0030 错误降级单元测试.

覆盖 acceptance.md AC-NFR0030-1~2:
- 数据源不可用 -> 表格上方显示 "数据加载失败, 正在重试..." + 倒计时
- trade-gateway 断开 -> 实盘策略详情页顶部出现黄色横幅 + 红色图标/文字 + 重试按钮
"""
from __future__ import annotations

import pytest

from quantide.web.nfr_error_degradation import (
    DEFAULT_RETRY_COUNTDOWN_SECONDS,
    data_unavailable_message,
    gateway_disconnect_banner,
)


class TestDataUnavailableMessage:
    """AC-NFR0030-1: 数据源不可用占位."""

    def test_message_contains_retry_text(self):
        msg = data_unavailable_message(seconds_until_retry=5)
        assert "数据加载失败" in msg
        assert "正在重试" in msg

    def test_message_includes_countdown(self):
        msg = data_unavailable_message(seconds_until_retry=3)
        assert "3" in msg


class TestGatewayDisconnectBanner:
    """AC-NFR0030-2: 网关断开横幅规范."""

    def test_banner_background_is_yellow(self):
        banner = gateway_disconnect_banner()
        assert banner["background"] == "yellow"

    def test_banner_text_and_icon_are_red(self):
        banner = gateway_disconnect_banner()
        assert banner["text_color"] == "red"
        assert banner["icon_color"] == "red"

    def test_banner_contains_warning_icon(self):
        banner = gateway_disconnect_banner()
        assert "⚠" in banner["icon"]

    def test_banner_contains_retry_button(self):
        banner = gateway_disconnect_banner()
        assert banner["retry_button"] is True

    def test_banner_message_contains_gateway(self):
        banner = gateway_disconnect_banner()
        assert "网关" in banner["message"]


class TestRetryCountdown:
    def test_default_countdown_positive(self):
        assert DEFAULT_RETRY_COUNTDOWN_SECONDS > 0
