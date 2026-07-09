"""FR-0120 单用户登录与会话单元测试.

覆盖 acceptance.md AC-FR0120-1~2:
- 正确用户名+密码 -> /dashboard 并建立会话
- 错误密码 5 次仍可继续尝试, 不锁定账号, 不记录到用户可见登录历史
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantide.web.services.auth_session import (
    AuthenticatedSession,
    LoginResult,
    authenticate,
    create_session,
    hash_password,
    login,
    verify_password,
)


class TestPasswordHashing:
    """密码哈希与校验基础."""

    def test_verify_correct_password(self):
        hashed = hash_password("secret")
        assert verify_password("secret", hashed) is True

    def test_verify_incorrect_password(self):
        hashed = hash_password("secret")
        assert verify_password("wrong", hashed) is False


class TestAuthenticate:
    """AC-FR0120-1: 正确凭据校验."""

    def test_authenticate_with_correct_password(self):
        hashed = hash_password("admin123")
        assert authenticate("admin", "admin123", hashed) is True

    def test_authenticate_with_wrong_password(self):
        hashed = hash_password("admin123")
        assert authenticate("admin", "wrong", hashed) is False


class TestCreateSession:
    """会话建立."""

    def test_session_contains_username_and_token(self):
        session = create_session("admin")
        assert session.username == "admin"
        assert session.session_token
        assert session.created_at <= datetime.now(timezone.utc)


class TestLogin:
    """AC-FR0120-1~2: 登录结果与会话."""

    def _user_loader(self, username: str):
        if username == "admin":
            return {"username": "admin", "password_hash": hash_password("admin123")}
        return None

    def test_login_success_redirects_to_dashboard(self):
        result = login("admin", "admin123", self._user_loader)
        assert isinstance(result, LoginResult)
        assert result.success is True
        assert result.redirect_to == "/dashboard"
        assert result.session is not None
        assert result.session.username == "admin"

    def test_login_failure_no_session(self):
        result = login("admin", "wrong", self._user_loader)
        assert result.success is False
        assert result.session is None
        assert result.redirect_to == "/login"

    def test_login_failure_unknown_user(self):
        result = login("nobody", "admin123", self._user_loader)
        assert result.success is False
        assert result.session is None

    def test_five_failed_attempts_still_allowed(self):
        """AC-FR0120-2: 连续错误 5 次后仍可继续尝试."""
        for _ in range(5):
            result = login("admin", "wrong", self._user_loader)
            assert result.success is False
        sixth = login("admin", "admin123", self._user_loader)
        assert sixth.success is True

    def test_failed_attempts_not_recorded_as_visible_history(self):
        """AC-FR0120-2: 连续错误不被记录到任何用户可见的登录历史."""
        result = login("admin", "wrong", self._user_loader)
        assert result.login_history is None
