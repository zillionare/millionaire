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


def read_persisted_state(
    storage: dict[str, object],
    key: str,
    *,
    default: str,
) -> str:
    """AC-NFR0070-4: 从 localStorage 读取状态, 失败时使用默认值.

    Args:
        storage: 模拟 localStorage 的字典.
        key: 状态 key (需在白名单内).
        default: 读取失败或 key 不存在时的默认值.

    Returns:
        存储值或默认值.
    """
    if not is_valid_local_storage_key(key):
        return default
    try:
        value = storage[key]
        if not isinstance(value, str):
            return default
        return value
    except (KeyError, TypeError):
        return default


def write_persisted_state(
    storage: dict[str, str],
    key: str,
    value: str,
) -> None:
    """AC-NFR0070-1~3, AC-5: 写入 localStorage 状态.

    仅允许白名单 key, 禁止写入敏感 key.

    Args:
        storage: 模拟 localStorage 的字典.
        key: 状态 key.
        value: 要写入的字符串值.

    Raises:
        ValueError: 当 key 不在白名单或含敏感信息.
    """
    if is_sensitive_key(key):
        raise ValueError(f"禁止将敏感信息写入 localStorage: {key}")
    if not is_valid_local_storage_key(key):
        raise ValueError(f"不允许的 localStorage key: {key}")
    storage[key] = value


__all__ = [
    "FORBIDDEN_KEYS",
    "LOCAL_STORAGE_KEYS",
    "is_sensitive_key",
    "is_valid_local_storage_key",
    "read_persisted_state",
    "write_persisted_state",
]
