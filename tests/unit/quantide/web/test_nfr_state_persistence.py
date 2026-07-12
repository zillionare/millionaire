"""NFR-0070 本地 UI 状态持久化单元测试.

覆盖 acceptance.md AC-NFR0070-1~5:
- 侧边栏折叠状态持久化 (key 白名单)
- 运行时参数默认值持久化
- 显示已隐藏账户开关持久化
- localStorage 读取失败时使用默认值
- localStorage 不存储敏感信息
"""
from __future__ import annotations

import pytest

from quantide.web.local_storage import (
    LOCAL_STORAGE_KEYS,
    read_persisted_state,
    write_persisted_state,
)


class TestReadPersistedState:
    """AC-NFR0070-4: 读取失败时使用默认值."""

    def test_returns_value_when_present(self):
        storage = {"quantide.sidebar.collapsed": "true"}
        value = read_persisted_state(
            storage, "quantide.sidebar.collapsed", default="false"
        )
        assert value == "true"

    def test_returns_default_when_missing(self):
        storage: dict[str, str] = {}
        value = read_persisted_state(
            storage, "quantide.sidebar.collapsed", default="false"
        )
        assert value == "false"

    def test_returns_default_when_invalid_json(self):
        storage = {"quantide.sidebar.collapsed": object()}  # type: ignore[dict-item]
        value = read_persisted_state(
            storage, "quantide.sidebar.collapsed", default="false"
        )
        assert value == "false"

    def test_returns_default_for_non_whitelisted_key(self):
        storage: dict[str, str] = {"unknown": "x"}
        value = read_persisted_state(storage, "unknown", default="default")
        assert value == "default"


class TestWritePersistedState:
    """AC-NFR0070-1~3, AC-5: 写入白名单 key, 禁止敏感 key."""

    def test_writes_whitelisted_key(self):
        storage: dict[str, str] = {}
        write_persisted_state(
            storage, "quantide.sidebar.collapsed", "true"
        )
        assert storage["quantide.sidebar.collapsed"] == "true"

    def test_rejects_unknown_key(self):
        storage: dict[str, str] = {}
        with pytest.raises(ValueError):
            write_persisted_state(storage, "quantide.unknown", "x")

    def test_rejects_sensitive_key(self):
        """AC-NFR0070-5: 不存储敏感信息."""
        storage: dict[str, str] = {}
        with pytest.raises(ValueError):
            write_persisted_state(storage, "password", "secret")

    def test_all_whitelisted_keys_are_non_sensitive(self):
        for key in LOCAL_STORAGE_KEYS:
            from quantide.web.local_storage import is_sensitive_key

            assert is_sensitive_key(key) is False
