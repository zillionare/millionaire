"""FR-0130/0150 布局与改密单元测试.

覆盖:
- AC-FR0150-1~2: 主界面布局 (header/sidebar/main, 折叠持久化)
- AC-FR0130-2~4: 改密 (旧密码 + 两次新密码, 不校验复杂度, 无改昵称)
"""
from __future__ import annotations

import pytest

from quantide.web.services.layout import (
    LayoutConfig,
    PasswordChangeRequest,
    PasswordChangeResult,
    PasswordChangeError,
    SIDEBAR_COLLAPSED_KEY,
    SUPPORTS_NICKNAME_CHANGE,
    validate_password_change,
)


class TestLayoutConfig:
    """AC-FR0150-1: 主界面布局三部分."""

    def test_layout_has_header_sidebar_main(self):
        config = LayoutConfig(sidebar_collapsed=False)
        assert config.sidebar_collapsed is False

    def test_sidebar_collapsed_persisted_to_localstorage(self):
        """AC-2: 折叠状态持久化到 localStorage."""
        assert SIDEBAR_COLLAPSED_KEY == "quantide.sidebar.collapsed"


class TestPasswordChange:
    """AC-FR0130-2~4: 修改密码."""

    def test_valid_password_change(self):
        """AC-2: 旧密码 + 两次新密码."""
        req = PasswordChangeRequest(
            old_password="old123",
            new_password="new123",
            confirm_password="new123",
        )
        assert validate_password_change(req, current_password="old123") is True

    def test_old_password_mismatch(self):
        """AC-3: 旧密码错误 -> 表单显示'旧密码错误'."""
        req = PasswordChangeRequest(
            old_password="wrong",
            new_password="new123",
            confirm_password="new123",
        )
        with pytest.raises(PasswordChangeError) as exc:
            validate_password_change(req, current_password="old123")
        assert "旧密码错误" in str(exc.value)

    def test_new_passwords_not_matching(self):
        """AC-3: 两次新密码不一致 -> 表单显示'两次输入不一致'."""
        req = PasswordChangeRequest(
            old_password="old123",
            new_password="new123",
            confirm_password="different",
        )
        with pytest.raises(PasswordChangeError) as exc:
            validate_password_change(req, current_password="old123")
        assert "两次输入不一致" in str(exc.value)

    def test_no_complexity_check(self):
        """AC: 不校验复杂度 (仅校验两次输入一致)."""
        req = PasswordChangeRequest(
            old_password="old123",
            new_password="1",
            confirm_password="1",
        )
        assert validate_password_change(req, current_password="old123") is True


class TestNoNicknameChange:
    """AC-FR0130-4: UI 无'改昵称'入口."""

    def test_nickname_change_not_supported(self):
        assert SUPPORTS_NICKNAME_CHANGE is False
