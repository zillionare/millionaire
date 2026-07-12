"""FR-0130/0150 布局与改密服务.

定义主界面布局配置 (header/sidebar/main) 与改密校验规则.

AC-FR0150-2: 侧边栏折叠状态持久化到 localStorage.
AC-FR0130-2: 改密需旧密码 + 两次新密码.
AC-FR0130-3: 旧密码错误/两次不一致的明确提示.
AC-FR0130-4: 无'改昵称'入口 (系统默认用户名 admin, 不支持昵称).
"""

from __future__ import annotations

from dataclasses import dataclass

SIDEBAR_COLLAPSED_KEY = "quantide.sidebar.collapsed"
SUPPORTS_NICKNAME_CHANGE = False


@dataclass
class LayoutConfig:
    """主界面布局配置 (AC-FR0150-1).

    Attributes:
        sidebar_collapsed: 侧边栏是否折叠 (持久化到 localStorage).
    """

    sidebar_collapsed: bool


class PasswordChangeError(ValueError):
    """改密校验错误."""


@dataclass
class PasswordChangeRequest:
    """AC-FR0130-2: 改密请求.

    Attributes:
        old_password: 旧密码.
        new_password: 新密码.
        confirm_password: 确认新密码.
    """

    old_password: str
    new_password: str
    confirm_password: str


@dataclass
class PasswordChangeResult:
    """改密结果.

    Attributes:
        ok: 是否成功.
        message: 结果消息.
    """

    ok: bool
    message: str


def validate_password_change(req: PasswordChangeRequest, *, current_password: str) -> bool:
    """AC-FR0130-3: 校验改密请求.

    旧密码错误 -> '旧密码错误'; 两次新密码不一致 -> '两次输入不一致'.
    不校验复杂度 (AC: 仅校验两次输入一致).

    Args:
        req: 改密请求.
        current_password: 当前密码 (用于校验旧密码).

    Returns:
        True 当旧密码正确且两次新密码一致.

    Raises:
        PasswordChangeError: 当旧密码错误或两次新密码不一致.
    """
    if req.old_password != current_password:
        raise PasswordChangeError("旧密码错误")
    if req.new_password != req.confirm_password:
        raise PasswordChangeError("两次输入不一致")
    return True


__all__ = [
    "SIDEBAR_COLLAPSED_KEY",
    "SUPPORTS_NICKNAME_CHANGE",
    "LayoutConfig",
    "PasswordChangeError",
    "PasswordChangeRequest",
    "PasswordChangeResult",
    "validate_password_change",
]
