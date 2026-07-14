"""B08-runtime-modes-1: Tests for quantide/core/runtime/modes.py.

Target: push coverage from 78.7% to >=80% by exercising
RuntimeBootstrap._resolve_mode and the basic structure.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from quantide.core.runtime import AdapterRegistry
from quantide.core.runtime.modes import RuntimeBootstrap, RuntimeContext
from quantide.service.registry import BrokerRegistry


# ---------------------------------------------------------------------------
# RuntimeContext structure
# ---------------------------------------------------------------------------


def test_runtime_context_has_expected_fields():
    """RuntimeContext is a dataclass-like with mode, registry, adapters, market_data, clock."""
    reg = BrokerRegistry()
    ctx = RuntimeContext(
        mode="paper",
        registry=reg,
        adapters=AdapterRegistry(),
        market_data=SimpleNamespace(),
        clock=SimpleNamespace(),
    )
    assert ctx.mode == "paper"
    assert ctx.registry is reg
    assert isinstance(ctx.adapters, AdapterRegistry)


def test_runtime_context_register_port_broker():
    """register_port_broker delegates to register_port_backed_broker (not mocked)."""
    from quantide.core.ports.broker import BrokerPort

    class _Port(BrokerPort):
        async def place_order(self, request):
            if False:
                yield None
        async def cancel_order(self, request):
            if False:
                yield None

    ctx = RuntimeContext(
        mode="paper",
        registry=BrokerRegistry(),
        adapters=AdapterRegistry(),
        market_data=SimpleNamespace(),
        clock=SimpleNamespace(),
    )
    result = ctx.register_port_broker(
        port=_Port(),
        portfolio_id="p1",
        kind="sim",
        adapter_name="ad",
    )
    # Real result is a PortBackedBroker wrapper; assert it's not None.
    assert result is not None


# ---------------------------------------------------------------------------
# RuntimeBootstrap.__init__
# ---------------------------------------------------------------------------


def test_bootstrap_init_with_explicit_mode():
    rb = RuntimeBootstrap(mode="backtest")
    assert rb._mode == "backtest"


def test_bootstrap_init_with_default_clock():
    rb = RuntimeBootstrap(mode="backtest")
    assert rb._clock is not None


def test_bootstrap_init_with_explicit_clock():
    fake_clock = SimpleNamespace()
    rb = RuntimeBootstrap(mode="backtest", clock=fake_clock)
    assert rb._clock is fake_clock


# ---------------------------------------------------------------------------
# RuntimeBootstrap._resolve_mode
# ---------------------------------------------------------------------------


def test_resolve_mode_returns_live_when_raw_is_live(monkeypatch):
    fake_settings = SimpleNamespace(
        runtime_mode="live", livequote_mode="gateway", gateway_enabled=True
    )
    monkeypatch.setattr(
        "quantide.core.runtime.modes.get_settings", lambda: fake_settings
    )
    rb = RuntimeBootstrap()
    assert rb._resolve_mode() == "live"


def test_resolve_mode_returns_paper_when_raw_is_paper(monkeypatch):
    fake_settings = SimpleNamespace(
        runtime_mode="paper", livequote_mode="none", gateway_enabled=False
    )
    monkeypatch.setattr(
        "quantide.core.runtime.modes.get_settings", lambda: fake_settings
    )
    rb = RuntimeBootstrap()
    assert rb._resolve_mode() == "paper"


def test_resolve_mode_returns_backtest_when_raw_is_backtest(monkeypatch):
    fake_settings = SimpleNamespace(
        runtime_mode="backtest", livequote_mode="none", gateway_enabled=False
    )
    monkeypatch.setattr(
        "quantide.core.runtime.modes.get_settings", lambda: fake_settings
    )
    rb = RuntimeBootstrap()
    assert rb._resolve_mode() == "backtest"


def test_resolve_mode_falls_back_to_backtest_when_livequote_none(monkeypatch):
    """When runtime_mode is unknown but livequote_mode is 'none', returns 'backtest'."""
    fake_settings = SimpleNamespace(
        runtime_mode="weird", livequote_mode="none", gateway_enabled=True
    )
    monkeypatch.setattr(
        "quantide.core.runtime.modes.get_settings", lambda: fake_settings
    )
    rb = RuntimeBootstrap()
    assert rb._resolve_mode() == "backtest"


def test_resolve_mode_falls_back_to_live_by_default(monkeypatch):
    """When raw mode is unknown and gateway is enabled, defaults to 'live'."""
    fake_settings = SimpleNamespace(
        runtime_mode="weird", livequote_mode="gateway", gateway_enabled=True
    )
    monkeypatch.setattr(
        "quantide.core.runtime.modes.get_settings", lambda: fake_settings
    )
    rb = RuntimeBootstrap()
    assert rb._resolve_mode() == "live"
