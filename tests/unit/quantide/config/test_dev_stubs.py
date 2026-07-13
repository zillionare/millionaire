"""Coverage tests for quantide.config.dev_stubs.

AC anchors: AC-FR0703-01 (config contract) — dev_stubs enable/disable switch.
"""

from __future__ import annotations

import importlib
import os
import socket
from typing import Any

import pytest

from quantide.config import dev_stubs as dev_stubs_module
from quantide.config.dev_stubs import (
    DEV_STUB_GATEWAY_API_KEY,
    DEV_STUB_GATEWAY_PASSWORD,
    DEV_STUB_GATEWAY_USERNAME,
    DEV_STUB_TUSHARE_TOKEN,
    DEV_STUBS_ENV_VAR,
    DevStubRuntime,
    dev_stubs_enabled,
    ensure_dev_stubs_started,
    reset_dev_stub_runtime_for_tests,
)


@pytest.fixture
def stub_modules(monkeypatch: pytest.MonkeyPatch):
    """Provide a fake gateway + tushare stub pair.

    Avoids hitting real network sockets and records start/stop calls.
    """

    class FakeGatewayStub:
        def __init__(self, prefix: str = "/qmt") -> None:
            self.prefix = prefix
            # bind a free local port to look realistic
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
            sock.close()
            self.base_url = f"http://127.0.0.1:{self.port}{prefix}"
            self.stopped = False
            self.stop_calls = 0

        def stop(self) -> None:
            self.stopped = True
            self.stop_calls += 1

    class FakeTusharePatch:
        def __init__(self) -> None:
            self.entered = False
            self.exited = False

        def __enter__(self) -> "FakeTusharePatch":
            self.entered = True
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            self.exited = True

    fake_gateway = FakeGatewayStub()
    fake_patch = FakeTusharePatch()

    gateway_module = importlib.import_module("tests.e2e.support.gateway_stub")
    tushare_module = importlib.import_module("tests.e2e.support.tushare_stub")

    monkeypatch.setattr(gateway_module, "start_gateway_stub", lambda prefix="/qmt": fake_gateway)
    monkeypatch.setattr(tushare_module, "patched_tushare_fetcher", lambda: fake_patch)

    reset_dev_stub_runtime_for_tests()
    yield fake_gateway, fake_patch
    reset_dev_stub_runtime_for_tests()


def test_dev_stubs_enabled_truthy_values_are_recognised(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-FR0703-01: QUANTIDE_ENABLE_DEV_STUBS accepts canonical truthy spellings."""
    for raw in ("1", "true", "yes", "on"):
        monkeypatch.setenv(DEV_STUBS_ENV_VAR, raw)
        assert dev_stubs_enabled() is True, raw
        assert dev_stubs_module.dev_stubs_enabled() is True
    for raw in ("0", "false", "no", "off", "", "  "):
        monkeypatch.setenv(DEV_STUBS_ENV_VAR, raw)
        assert dev_stubs_enabled() is False, raw


def test_dev_stubs_enabled_unset_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-FR0703-01: missing env var means stubs are off."""
    monkeypatch.delenv(DEV_STUBS_ENV_VAR, raising=False)
    assert dev_stubs_enabled() is False
    assert dev_stubs_module._DEV_STUB_RUNTIME is None


def test_ensure_dev_stubs_started_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-FR0703-01: when switch is off, no runtime is created."""
    monkeypatch.delenv(DEV_STUBS_ENV_VAR, raising=False)
    reset_dev_stub_runtime_for_tests()
    assert ensure_dev_stubs_started() is None
    assert dev_stubs_module._DEV_STUB_RUNTIME is None


def test_ensure_dev_stubs_started_constructs_runtime_when_enabled(
    monkeypatch: pytest.MonkeyPatch, stub_modules
) -> None:
    """AC-FR0703-01: enabling the switch wires up gateway + tushare fixtures."""
    fake_gateway, fake_patch = stub_modules
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "1")

    runtime = ensure_dev_stubs_started()

    assert isinstance(runtime, DevStubRuntime)
    assert runtime.gateway_base_url == fake_gateway.base_url
    assert runtime.gateway_port == fake_gateway.port
    assert runtime.gateway_scheme == "http"
    assert runtime.gateway_prefix == "/qmt"
    assert runtime.gateway_api_key == DEV_STUB_GATEWAY_API_KEY
    assert runtime.gateway_username == DEV_STUB_GATEWAY_USERNAME
    assert runtime.gateway_password == DEV_STUB_GATEWAY_PASSWORD
    assert fake_patch.entered is True
    assert dev_stubs_module._DEV_STUB_RUNTIME is runtime


def test_ensure_dev_stubs_started_returns_existing_runtime_idempotently(
    monkeypatch: pytest.MonkeyPatch, stub_modules
) -> None:
    """AC-FR0703-01: second invocation returns the cached runtime without re-starting."""
    fake_gateway, fake_patch = stub_modules
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "true")

    first = ensure_dev_stubs_started()
    second = ensure_dev_stubs_started()

    assert first is second
    assert fake_patch.entered is True  # only entered once
    assert fake_gateway.stopped is False


def test_stop_dev_stubs_releases_runtime_and_calls_teardown(
    monkeypatch: pytest.MonkeyPatch, stub_modules
) -> None:
    """AC-FR0703-01: explicit stop clears global state and stops both stubs."""
    fake_gateway, fake_patch = stub_modules
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "yes")

    runtime = ensure_dev_stubs_started()
    assert dev_stubs_module._DEV_STUB_RUNTIME is runtime

    dev_stubs_module._stop_dev_stubs()

    assert dev_stubs_module._DEV_STUB_RUNTIME is None
    assert fake_patch.exited is True
    assert fake_gateway.stopped is True
    assert fake_gateway.stop_calls == 1


def test_stop_dev_stubs_is_noop_when_runtime_missing() -> None:
    """AC-FR0703-01: stop without an active runtime must not raise."""
    assert dev_stubs_module._DEV_STUB_RUNTIME is None
    dev_stubs_module._stop_dev_stubs()  # must not raise
    assert dev_stubs_module._DEV_STUB_RUNTIME is None


def test_reset_dev_stub_runtime_for_tests_clears_runtime(
    monkeypatch: pytest.MonkeyPatch, stub_modules
) -> None:
    """AC-FR0703-01: tests must reset runtime between runs to stay isolated."""
    fake_gateway, _ = stub_modules
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "on")

    ensure_dev_stubs_started()
    assert dev_stubs_module._DEV_STUB_RUNTIME is not None

    reset_dev_stub_runtime_for_tests()

    assert dev_stubs_module._DEV_STUB_RUNTIME is None
    assert fake_gateway.stopped is True


def test_ensure_dev_stubs_started_raises_when_stubs_import_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-FR0703-01: enabling stubs without the e2e support module must fail loudly."""
    import sys

    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "1")
    reset_dev_stub_runtime_for_tests()

    # Force ImportError by hiding the e2e support modules
    for mod_name in list(sys.modules):
        if mod_name.startswith("tests.e2e.support"):
            monkeypatch.delitem(sys.modules, mod_name)

    real_import = __import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in {"tests.e2e.support.gateway_stub", "tests.e2e.support.tushare_stub"}:
            raise ImportError("blocked for test")
        if name.startswith("tests.e2e.support.gateway_stub") or name.startswith(
            "tests.e2e.support.tushare_stub"
        ):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    monkeypatch.setattr(dev_stubs_module, "_DEV_STUB_RUNTIME", None)

    with pytest.raises(RuntimeError, match="开发 stub 模式依赖"):
        ensure_dev_stubs_started()


def test_dev_stubs_module_exports_public_api() -> None:
    """AC-FR0703-01: the documented public symbols remain exported."""
    assert hasattr(dev_stubs_module, "DEV_STUBS_ENV_VAR")
    assert hasattr(dev_stubs_module, "DEV_STUB_GATEWAY_API_KEY")
    assert hasattr(dev_stubs_module, "DEV_STUB_GATEWAY_PASSWORD")
    assert hasattr(dev_stubs_module, "DEV_STUB_GATEWAY_USERNAME")
    assert hasattr(dev_stubs_module, "DEV_STUB_TUSHARE_TOKEN")
    assert hasattr(dev_stubs_module, "DevStubRuntime")
    assert hasattr(dev_stubs_module, "dev_stubs_enabled")
    assert hasattr(dev_stubs_module, "ensure_dev_stubs_started")
    assert hasattr(dev_stubs_module, "reset_dev_stub_runtime_for_tests")
    assert DEV_STUBS_ENV_VAR == "QUANTIDE_ENABLE_DEV_STUBS"
    assert DEV_STUB_TUSHARE_TOKEN == "stub-token"
