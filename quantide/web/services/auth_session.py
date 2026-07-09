"""FR-0120 单用户登录与会话服务.

提供与具体 Web 框架无关的登录/session 纯逻辑, 便于单元测试:
- AC-FR0120-1: 正确用户名+密码 -> /dashboard 并建立会话.
- AC-FR0120-2: 错误密码不锁定账号, 且不记录到用户可见登录历史.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_SALT_BYTES = 16
_PBKDF2_ITERATIONS = 100_000


@dataclass(frozen=True)
class AuthenticatedSession:
    """已认证会话.

    Attributes:
        username: 登录用户名.
        session_token: 会话令牌 (仅服务端传递, 不写入 localStorage).
        created_at: 会话创建时间 (UTC).
    """

    username: str
    session_token: str
    created_at: datetime


@dataclass(frozen=True)
class LoginResult:
    """登录结果.

    Attributes:
        success: 是否登录成功.
        redirect_to: 登录成功/失败后应跳转的路径.
        session: 成功时建立的会话, 失败为 None.
        message: 提示文案.
        login_history: 始终为 None, 表示不对外暴露登录历史.
    """

    success: bool
    redirect_to: str
    session: AuthenticatedSession | None
    message: str
    login_history: None = None


def hash_password(password: str) -> str:
    """对密码进行 PBKDF2 哈希.

    Args:
        password: 明文密码.

    Returns:
        salt$hex_key 格式字符串.
    """
    salt = secrets.token_hex(_SALT_BYTES)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    ).hex()
    return f"{salt}${key}"


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码是否与存储哈希匹配.

    Args:
        password: 明文密码.
        password_hash: hash_password 产生的 salt$hex_key.

    Returns:
        匹配返回 True, 否则 False.
    """
    try:
        salt, stored_key = password_hash.split("$", 1)
    except ValueError:
        return False
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    ).hex()
    return hmac.compare_digest(key, stored_key)


def authenticate(username: str, password: str, password_hash: str | None) -> bool:
    """校验用户名密码.

    Args:
        username: 用户名 (仅用于语义, 不参与哈希).
        password: 明文密码.
        password_hash: 存储的密码哈希, None 表示用户不存在.

    Returns:
        密码正确返回 True.
    """
    if password_hash is None:
        return False
    return verify_password(password, password_hash)


def create_session(username: str) -> AuthenticatedSession:
    """为用户创建会话.

    Args:
        username: 登录成功的用户名.

    Returns:
        AuthenticatedSession.
    """
    token = secrets.token_urlsafe(32)
    return AuthenticatedSession(
        username=username,
        session_token=token,
        created_at=datetime.now(timezone.utc),
    )


def login(
    username: str,
    password: str,
    user_loader: Callable[[str], dict[str, Any] | None],
) -> LoginResult:
    """执行登录并返回结果.

    AC-FR0120-2: 无论失败多少次都不会锁定账号, 也不会记录用户可见登录历史.

    Args:
        username: 用户名.
        password: 明文密码.
        user_loader: 根据用户名加载用户字典 (需包含 password_hash) 的回调.

    Returns:
        LoginResult, 成功时 redirect_to 为 /dashboard.
    """
    user = user_loader(username)
    if user is None or not authenticate(
        username, password, user.get("password_hash")
    ):
        return LoginResult(
            success=False,
            redirect_to="/login",
            session=None,
            message="用户名或密码错误",
        )
    session = create_session(username)
    return LoginResult(
        success=True,
        redirect_to="/dashboard",
        session=session,
        message="登录成功",
    )


__all__ = [
    "AuthenticatedSession",
    "LoginResult",
    "authenticate",
    "create_session",
    "hash_password",
    "login",
    "verify_password",
]
