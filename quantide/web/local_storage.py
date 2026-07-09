"""localStorage key 契约 (interfaces.md §6, NFR-0070).

仅保存非敏感 UI 状态 (sidebar / filter / runtime defaults).
禁止存储: password, session token, Tushare token, qmt-gateway api_key.
"""

from __future__ import annotations

LOCAL_STORAGE_KEYS: frozenset[str] = frozenset(
    {
        "quantide.sidebar.collapsed",
        "quantide.accounts.display_hidden",
        "quantide.runtime_params.last",
        "quantide.filters.strategy",
        "quantide.wizard.pending_banner.dismissed_at",
    }
)

FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "session_token",
        "tushare_token",
        "qmt_gateway_api_key",
        "api_key",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    }
)

_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
)


def is_valid_local_storage_key(key: str) -> bool:
    """判断 key 是否在白名单内.

    Args:
        key: localStorage key.

    Returns:
        True 当 key 在 LOCAL_STORAGE_KEYS 白名单内.
    """
    return key in LOCAL_STORAGE_KEYS


def is_sensitive_key(key: str) -> bool:
    """NFR-0070 AC-5: 判断 key 是否含敏感信息.

    禁止 key: password, session token, Tushare token, qmt-gateway api_key.

    Args:
        key: localStorage key.

    Returns:
        True 当 key 在禁止集合或含敏感子串.
    """
    lowered = key.lower()
    if lowered in FORBIDDEN_KEYS:
        return True
    return any(sub in lowered for sub in _SENSITIVE_SUBSTRINGS)


__all__ = [
    "FORBIDDEN_KEYS",
    "LOCAL_STORAGE_KEYS",
    "is_sensitive_key",
    "is_valid_local_storage_key",
]
