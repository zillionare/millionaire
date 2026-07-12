"""FR-0110/0120/0140 启动路由分流与登录重定向单元测试.

覆盖:
- AC-FR0110-1~2: 未初始化 -> wizard; 已初始化未登录 -> /login
- AC-FR0140-1~2: 未登录访问受保护页面 -> /login?next=...; 登录后跳回
"""
from __future__ import annotations

import pytest

from quantide.web.services.routing import (
    determine_root_redirect,
    build_login_redirect,
    extract_next_path,
    is_protected_path,
    is_public_path,
)


class TestRootRedirect:
    """AC-FR0110-1~2: 启动路由分流."""

    def test_uninitialized_redirects_to_wizard(self):
        """AC-1: 全新安装访问 / -> 跳转到 init-wizard."""
        target = determine_root_redirect(initialized=False, authenticated=False)
        assert target == "/init-wizard"

    def test_initialized_unauthenticated_redirects_to_login(self):
        """AC-2: 已初始化未登录访问 / -> 重定向到 /login."""
        target = determine_root_redirect(initialized=True, authenticated=False)
        assert target == "/login"

    def test_initialized_authenticated_goes_dashboard(self):
        target = determine_root_redirect(initialized=True, authenticated=True)
        assert target == "/dashboard"


class TestProtectedPath:
    """AC-FR0110-1: 未初始化时访问非 wizard 路径 -> 重定向到 wizard."""

    def test_dashboard_is_protected(self):
        assert is_protected_path("/dashboard") is True

    def test_wizard_is_public(self):
        assert is_public_path("/init-wizard") is True

    def test_static_is_public(self):
        assert is_public_path("/static/css/app.css") is True

    def test_health_is_public(self):
        assert is_public_path("/api/health") is True


class TestLoginRedirect:
    """AC-FR0140-1~2: 未登录访问重定向到 /login?next=..."""

    def test_login_redirect_preserves_next(self):
        """AC-1: 未登录访问 /dashboard/accounts/123 -> /login?next=/dashboard/accounts/123."""
        redirect = build_login_redirect(original_path="/dashboard/accounts/123")
        assert "/login" in redirect
        assert "next=/dashboard/accounts/123" in redirect

    def test_extract_next_path(self):
        """AC-2: 登录成功后跳回 next 路径."""
        next_path = extract_next_path("/login?next=/dashboard/accounts/123")
        assert next_path == "/dashboard/accounts/123"

    def test_extract_next_none_when_absent(self):
        next_path = extract_next_path("/login")
        assert next_path is None
