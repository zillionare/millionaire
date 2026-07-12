"""FR-0110/0120/0140 启动路由分流与登录重定向服务.

定义根据初始化/登录状态的路由分流规则与 deep link 保留.

AC-FR0110-1: 未初始化访问任何非 wizard 路径 -> 重定向到 wizard 欢迎页.
AC-FR0110-2: 已初始化未登录访问 / -> 重定向到 /login.
AC-FR0140-1: 未登录访问受保护页面 -> /login?next=原路径.
AC-FR0140-2: 登录成功后跳回原路径 (deep link 保留).
"""

from __future__ import annotations

from urllib.parse import parse_qs, quote, urlparse

_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/init-wizard",
    "/static",
    "/api/health",
    "/auth/login",
)


def determine_root_redirect(*, initialized: bool, authenticated: bool) -> str:
    """AC-FR0110-1~2: 根据 init/login 状态决定 / 的重定向目标.

    Args:
        initialized: 系统是否已初始化.
        authenticated: 当前用户是否已登录.

    Returns:
        重定向目标路径: /init-wizard (未初始化), /login (已初始化未登录), /dashboard (已登录).
    """
    if not initialized:
        return "/init-wizard"
    if not authenticated:
        return "/login"
    return "/dashboard"


def is_public_path(path: str) -> bool:
    """判断路径是否为公开路径 (无需 init/login 即可访问).

    Args:
        path: 请求路径.

    Returns:
        True 当路径以公开前缀开头.
    """
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def is_protected_path(path: str) -> bool:
    """判断路径是否为受保护路径.

    Args:
        path: 请求路径.

    Returns:
        True 当路径非公开路径.
    """
    return not is_public_path(path)


def build_login_redirect(original_path: str) -> str:
    """AC-FR0140-1: 构建登录重定向 URL, 保留 deep link.

    Args:
        original_path: 用户原本想访问的路径.

    Returns:
        /login?next=原路径.
    """
    query = f"next={quote(original_path, safe='/')}"
    return f"/login?{query}"


def extract_next_path(login_url: str) -> str | None:
    """AC-FR0140-2: 从登录 URL 提取 next 参数.

    Args:
        login_url: 登录 URL (可能含 ?next=...).

    Returns:
        next 路径; 无 next 时返回 None.
    """
    parsed = urlparse(login_url)
    params = parse_qs(parsed.query)
    next_values = params.get("next")
    return next_values[0] if next_values else None


__all__ = [
    "build_login_redirect",
    "determine_root_redirect",
    "extract_next_path",
    "is_protected_path",
    "is_public_path",
]
