"""Development-only local stub runtime.

This module is intentionally opt-in. When the environment variable
`QUANTIDE_ENABLE_DEV_STUBS` is enabled, the process will:

1. start a local scriptable gateway stub, and
2. replace the default `tushare` fetcher with fixture-backed data.

The goal is to let developers run the real application against deterministic
local doubles without changing persisted application settings.
"""

from __future__ import annotations

import atexit
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from loguru import logger


DEV_STUBS_ENV_VAR = "QUANTIDE_ENABLE_DEV_STUBS"
DEV_STUB_TUSHARE_TOKEN = "stub-token"
DEV_STUB_GATEWAY_API_KEY = "stub-api-key"
DEV_STUB_GATEWAY_USERNAME = "stub-user"
DEV_STUB_GATEWAY_PASSWORD = "stub-password"

_ENABLED_VALUES = {"1", "true", "yes", "on"}


@dataclass(slots=True)
class DevStubRuntime:
    """Process-lifetime development stub runtime."""

    gateway_base_url: str
    gateway_scheme: str
    gateway_server: str
    gateway_port: int
    gateway_prefix: str
    gateway_api_key: str
    gateway_username: str
    gateway_password: str
    _gateway_stub: Any
    _tushare_patch: Any

    def stop(self) -> None:
        """Stop the running stubs and restore patched fetchers."""
        try:
            self._gateway_stub.stop()
        finally:
            self._tushare_patch.__exit__(None, None, None)


_DEV_STUB_RUNTIME: DevStubRuntime | None = None


def dev_stubs_enabled() -> bool:
    """Return whether development stub mode is enabled."""
    value = str(os.getenv(DEV_STUBS_ENV_VAR, "")).strip().lower()
    return value in _ENABLED_VALUES


def ensure_dev_stubs_started() -> DevStubRuntime | None:
    """Start development stubs once per process when the switch is enabled."""
    global _DEV_STUB_RUNTIME

    if not dev_stubs_enabled():
        return None
    if _DEV_STUB_RUNTIME is not None:
        return _DEV_STUB_RUNTIME

    try:
        from tests.e2e.support.gateway_stub import start_gateway_stub
        from tests.e2e.support.tushare_stub import patched_tushare_fetcher
    except ImportError as exc:
        raise RuntimeError(
            "开发 stub 模式依赖仓库内的 tests/e2e/support 目录，请在源码仓库中运行。"
        ) from exc

    tushare_patch = patched_tushare_fetcher()
    tushare_patch.__enter__()
    gateway_stub = start_gateway_stub(prefix="/qmt")
    parsed = urlparse(gateway_stub.base_url)
    _DEV_STUB_RUNTIME = DevStubRuntime(
        gateway_base_url=gateway_stub.base_url,
        gateway_scheme=parsed.scheme or "http",
        gateway_server=parsed.hostname or "127.0.0.1",
        gateway_port=int(parsed.port or 80),
        gateway_prefix=parsed.path or "/",
        gateway_api_key=DEV_STUB_GATEWAY_API_KEY,
        gateway_username=DEV_STUB_GATEWAY_USERNAME,
        gateway_password=DEV_STUB_GATEWAY_PASSWORD,
        _gateway_stub=gateway_stub,
        _tushare_patch=tushare_patch,
    )
    atexit.register(_stop_dev_stubs)
    logger.warning(
        "开发 stub 模式已启用: gateway={} tushare=fixture-backed",
        _DEV_STUB_RUNTIME.gateway_base_url,
    )
    return _DEV_STUB_RUNTIME


def _stop_dev_stubs() -> None:
    """Stop the global development stub runtime if it is running."""
    global _DEV_STUB_RUNTIME

    if _DEV_STUB_RUNTIME is None:
        return
    _DEV_STUB_RUNTIME.stop()
    _DEV_STUB_RUNTIME = None


def reset_dev_stub_runtime_for_tests() -> None:
    """Reset the global runtime for isolated tests."""
    _stop_dev_stubs()


__all__ = [
    "DEV_STUBS_ENV_VAR",
    "DEV_STUB_GATEWAY_API_KEY",
    "DEV_STUB_GATEWAY_PASSWORD",
    "DEV_STUB_GATEWAY_USERNAME",
    "DEV_STUB_TUSHARE_TOKEN",
    "DevStubRuntime",
    "dev_stubs_enabled",
    "ensure_dev_stubs_started",
    "reset_dev_stub_runtime_for_tests",
]