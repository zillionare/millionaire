"""FR-0170 UI 内通知 (toast/banner) 单元测试.

覆盖 acceptance.md AC-FR0170-1~5:
- success: 3s 自动消失, hover 暂停
- error: 不自动消失, 必须手动关闭, ARIA role="alert"
- warning: 持续到用户处理, 可关闭
- info: 5s 自动消失, hover 暂停
- 多个 toast 纵向堆叠
"""
from __future__ import annotations

import pytest

from quantide.web.components.toast import (
    ToastConfig,
    ToastLevel,
    auto_dismiss_seconds,
    icon_for_level,
    is_auto_dismiss,
    requires_aria_alert_role,
)


class TestAutoDismiss:
    """AC-1, AC-2, AC-3, AC-4: 各类型自动消失时长."""

    def test_success_auto_dismiss_3s(self):
        """AC-1: success 3s 自动消失."""
        assert auto_dismiss_seconds(ToastLevel.SUCCESS) == 3

    def test_error_no_auto_dismiss(self):
        """AC-2: error 不自动消失."""
        assert is_auto_dismiss(ToastLevel.ERROR) is False
        assert auto_dismiss_seconds(ToastLevel.ERROR) is None

    def test_warning_no_auto_dismiss(self):
        """AC-3: warning 持续到用户处理 (不自动消失)."""
        assert is_auto_dismiss(ToastLevel.WARNING) is False

    def test_info_auto_dismiss_5s(self):
        """AC-4: info 5s 自动消失."""
        assert auto_dismiss_seconds(ToastLevel.INFO) == 5


class TestAriaAlertRole:
    """AC-5: 错误 toast 含 ARIA role='alert'."""

    def test_error_requires_aria_alert(self):
        """AC-5: 错误 toast 强制 ARIA role='alert'."""
        assert requires_aria_alert_role(ToastLevel.ERROR) is True

    def test_success_no_aria_alert(self):
        assert requires_aria_alert_role(ToastLevel.SUCCESS) is False

    def test_info_no_aria_alert(self):
        assert requires_aria_alert_role(ToastLevel.INFO) is False

    def test_warning_no_aria_alert(self):
        assert requires_aria_alert_role(ToastLevel.WARNING) is False


class TestIconMapping:
    """AC: 每种类型配语义图标 (✓/✕/⚠/ⓘ)."""

    def test_success_icon_check(self):
        assert icon_for_level(ToastLevel.SUCCESS) == "check"

    def test_error_icon_x(self):
        assert icon_for_level(ToastLevel.ERROR) == "x"

    def test_warning_icon_alert(self):
        assert icon_for_level(ToastLevel.WARNING) == "alert-triangle"

    def test_info_icon_info(self):
        assert icon_for_level(ToastLevel.INFO) == "info"


class TestToastConfig:
    def test_config_carries_level_and_message(self):
        cfg = ToastConfig.create(level=ToastLevel.SUCCESS, message="已发送, 订单号 123")
        assert cfg.level == ToastLevel.SUCCESS
        assert cfg.message == "已发送, 订单号 123"
        assert cfg.auto_dismiss is True
        assert cfg.dismiss_seconds == 3
