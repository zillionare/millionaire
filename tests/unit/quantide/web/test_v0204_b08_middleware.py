"""B08-middleware-1: Tests for quantide/web/middleware.py.

Target: raise coverage from 60.9% to >=80%.
"""

from __future__ import annotations

import pytest

from quantide.core.errors import BaseTradeError, WebErrors
from quantide.web.middleware import BrokerRegistryMiddleware, exception_handler


# ---------------------------------------------------------------------------
# BrokerRegistryMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broker_registry_middleware_sets_registry_for_http():
    middleware = BrokerRegistryMiddleware(app=_passthrough_app, registry="fake-reg")
    scope = {"type": "http"}
    receive = _passthrough_receive
    send = _passthrough_send
    await middleware(scope, receive, send)
    assert scope["registry"] == "fake-reg"


@pytest.mark.asyncio
async def test_broker_registry_middleware_skips_lifespan_scope():
    middleware = BrokerRegistryMiddleware(app=_passthrough_app, registry="fake-reg")
    scope = {"type": "lifespan"}
    receive = _passthrough_receive
    send = _passthrough_send
    await middleware(scope, receive, send)
    # lifespan scope should NOT have registry injected.
    assert "registry" not in scope


@pytest.mark.asyncio
async def test_broker_registry_middleware_handles_websocket():
    middleware = BrokerRegistryMiddleware(app=_passthrough_app, registry="fake-reg-ws")
    scope = {"type": "websocket"}
    await middleware(scope, _passthrough_receive, _passthrough_send)
    assert scope["registry"] == "fake-reg-ws"


# ---------------------------------------------------------------------------
# exception_handler
# ---------------------------------------------------------------------------


def _make_trade_error_with_code() -> BaseTradeError:
    from quantide.core.errors import TradeErrors
    return BaseTradeError(code=TradeErrors.ERROR_NOT_LOGIN, msg="trade-error")


import pytest


@pytest.mark.asyncio
async def test_exception_handler_handles_base_trade_error():
    err = _make_trade_error_with_code()
    resp = await exception_handler(None, err)  # type: ignore[arg-type]
    assert resp.status_code == 400
    body = resp.body
    assert b"trade-error" in body


@pytest.mark.asyncio
async def test_exception_handler_handles_unknown_error():
    resp = await exception_handler(None, ValueError("boom"))  # type: ignore[arg-type]
    assert resp.status_code == 500
    assert b"boom" in resp.body


@pytest.mark.asyncio
async def test_exception_handler_includes_traceback():
    """traceback is included in error_info."""
    err = _make_trade_error_with_code()
    resp = await exception_handler(None, err)  # type: ignore[arg-type]
    body = resp.body.decode("utf-8")
    assert "traceback" in body


@pytest.mark.asyncio
async def test_exception_handler_uses_web_errors_code_for_unknown():
    """Unknown errors use WebErrors.INTERNAL_SERVER_ERROR enum value."""
    err = ValueError("xyz")
    resp = await exception_handler(None, err)  # type: ignore[arg-type]
    body = resp.body.decode("utf-8")
    assert str(WebErrors.INTERNAL_SERVER_ERROR.value) in body


@pytest.mark.asyncio
async def test_exception_handler_preserves_class_name():
    """The 'type' field has the exception class name."""
    err = _make_trade_error_with_code()
    resp = await exception_handler(None, err)  # type: ignore[arg-type]
    body = resp.body.decode("utf-8")
    assert "BaseTradeError" in body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _passthrough_app(scope, receive, send):
    """Minimal ASGI app that does nothing."""
    if "type" in scope and scope["type"] == "http":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


async def _passthrough_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


async def _passthrough_send(message):
    pass
