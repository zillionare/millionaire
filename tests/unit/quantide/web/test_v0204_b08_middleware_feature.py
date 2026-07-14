"""B08-middleware-feature-1: Tests for quantide/web/middleware_feature.py.

Target: raise coverage from 70% to >=80%.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.middleware_feature import (
    FEATURE_ROUTE_PREFIXES,
    FeatureCheckMiddleware,
    _disabled_fragment_html,
    _disabled_page_html,
    _feature_disabled_response,
    _is_htmx_request,
    _match_feature_for_path,
    get_feature_status,
    require_qmt_configured,
)


# ---------------------------------------------------------------------------
# _match_feature_for_path
# ---------------------------------------------------------------------------


def test_match_feature_for_path_exact():
    assert _match_feature_for_path("/trade/simulation") == "simulation"


def test_match_feature_for_path_prefix():
    assert _match_feature_for_path("/trade/simulation/orders/1") == "simulation"


def test_match_feature_for_path_live_trading():
    assert _match_feature_for_path("/trade/live") == "live_trading"


def test_match_feature_for_path_no_match():
    assert _match_feature_for_path("/trade/paper") is None
    assert _match_feature_for_path("/home") is None


def test_match_feature_for_path_partial_no_match():
    """Path that contains prefix substring but doesn't start with it doesn't match."""
    assert _match_feature_for_path("/api/trade/simulation") is None


# ---------------------------------------------------------------------------
# _is_htmx_request
# ---------------------------------------------------------------------------


def test_is_htmx_request_true():
    headers = {"HX-Request": "true"}
    assert _is_htmx_request(headers) is True


def test_is_htmx_request_false():
    headers = {"HX-Request": "false"}
    assert _is_htmx_request(headers) is False


def test_is_htmx_request_missing():
    headers = {}
    assert _is_htmx_request(headers) is False


# ---------------------------------------------------------------------------
# _disabled_fragment_html / _disabled_page_html
# ---------------------------------------------------------------------------


def test_disabled_fragment_html_contains_feature_name():
    html = _disabled_fragment_html("实盘交易")
    assert "实盘交易" in html


def test_disabled_page_html_contains_product_and_feature():
    html = _disabled_page_html("Simulation")
    assert "<!DOCTYPE html>" in html
    assert "Simulation" in html


# ---------------------------------------------------------------------------
# _feature_disabled_response
# ---------------------------------------------------------------------------


def test_feature_disabled_response_htmx_fragment():
    resp = _feature_disabled_response("Test Feature", htmx=True)
    assert resp.status_code == 503
    # HTMLResponse — body has fragment content
    body = resp.body.decode("utf-8")
    assert "Test Feature" in body
    assert "<!DOCTYPE html>" not in body


def test_feature_disabled_response_full_page():
    resp = _feature_disabled_response("Test Feature", htmx=False)
    assert resp.status_code == 503
    body = resp.body.decode("utf-8")
    assert "<!DOCTYPE html>" in body
    assert "Test Feature" in body


# ---------------------------------------------------------------------------
# FeatureCheckMiddleware
# ---------------------------------------------------------------------------


def _build_request(path: str = "/trade/simulation", method: str = "GET",
                  hx_request: str = ""):
    req = MagicMock()
    req.url.path = path
    req.method = method
    req.headers = {"HX-Request": hx_request} if hx_request else {}
    return req


@pytest.mark.asyncio
async def test_middleware_passes_through_unrelated_path():
    """Non-trading paths are passed through."""
    middleware = FeatureCheckMiddleware(app=MagicMock())
    req = _build_request("/home")
    call_next = AsyncMock(return_value="OK")
    out = await middleware.dispatch(req, call_next)
    assert out == "OK"
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_passes_through_when_feature_available():
    """When feature is available, request flows through."""
    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"simulation": {"available": True, "name": "Sim"}},
    ):
        middleware = FeatureCheckMiddleware(app=MagicMock())
        req = _build_request("/trade/simulation")
        call_next = AsyncMock(return_value="OK")
        out = await middleware.dispatch(req, call_next)
        assert out == "OK"


@pytest.mark.asyncio
async def test_middleware_blocks_get_when_feature_unavailable():
    """GET to disabled feature returns 503 HTML."""
    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"simulation": {"available": False, "name": "Sim"}},
    ):
        middleware = FeatureCheckMiddleware(app=MagicMock())
        req = _build_request("/trade/simulation", method="GET")
        call_next = AsyncMock()
        out = await middleware.dispatch(req, call_next)
        assert out.status_code == 503
        assert "Sim" in out.body.decode("utf-8")


@pytest.mark.asyncio
async def test_middleware_blocks_get_htmx_when_feature_unavailable():
    """HTMX GET to disabled feature returns 503 fragment."""
    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"simulation": {"available": False, "name": "Sim"}},
    ):
        middleware = FeatureCheckMiddleware(app=MagicMock())
        req = _build_request("/trade/simulation", method="GET", hx_request="true")
        call_next = AsyncMock()
        out = await middleware.dispatch(req, call_next)
        assert out.status_code == 503


@pytest.mark.asyncio
async def test_middleware_blocks_post_when_feature_unavailable():
    """POST to disabled feature returns 503 JSON."""
    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"simulation": {"available": False, "name": "Sim"}},
    ):
        middleware = FeatureCheckMiddleware(app=MagicMock())
        req = _build_request("/trade/simulation", method="POST")
        call_next = AsyncMock()
        out = await middleware.dispatch(req, call_next)
        assert out.status_code == 503
        assert b"Sim" in out.body


@pytest.mark.asyncio
async def test_middleware_live_trading_blocked():
    """/trade/live with feature unavailable → block."""
    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"live_trading": {"available": False, "name": "LiveTrade"}},
    ):
        middleware = FeatureCheckMiddleware(app=MagicMock())
        req = _build_request("/trade/live", method="GET")
        call_next = AsyncMock()
        out = await middleware.dispatch(req, call_next)
        assert out.status_code == 503


# ---------------------------------------------------------------------------
# require_qmt_configured
# ---------------------------------------------------------------------------


def test_require_qmt_configured_passes_when_available():
    @require_qmt_configured
    def my_func():
        return "OK"

    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"live_trading": {"available": True}},
    ):
        assert my_func() == "OK"


def test_require_qmt_configured_blocks_when_unavailable():
    @require_qmt_configured
    def my_func():
        return "OK"

    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"live_trading": {"available": False}},
    ):
        out = my_func()
    assert out is not None  # return a response


def test_require_qmt_configured_preserves_name_kwarg():
    """When name is missing in feature config, uses fallback '实盘交易'."""
    @require_qmt_configured
    def my_func():
        return "OK"

    with patch(
        "quantide.web.middleware_feature.get_feature_status",
        return_value={"live_trading": {"available": False}},  # no name
    ):
        out = my_func()
    assert out is not None


# ---------------------------------------------------------------------------
# get_feature_status
# ---------------------------------------------------------------------------


def test_get_feature_status_returns_three_features():
    fake_wizard = MagicMock()
    fake_wizard.get_feature_status.return_value = {
        "backtest": True, "simulation": True, "live_trading": False
    }
    with patch(
        "quantide.web.middleware_feature.init_wizard", fake_wizard,
    ):
        features = get_feature_status()
    assert "backtest" in features
    assert "simulation" in features
    assert "live_trading" in features
    assert features["live_trading"]["available"] is False
    assert features["backtest"]["available"] is True


def test_get_feature_status_handles_exception():
    """When init_wizard raises, returns defaults with all unavailable."""
    fake_wizard = MagicMock()
    fake_wizard.get_feature_status.side_effect = Exception("boom")
    with patch(
        "quantide.web.middleware_feature.init_wizard", fake_wizard,
    ):
        features = get_feature_status()
    # All defaults are unavailable.
    for f in ("backtest", "simulation", "live_trading"):
        assert f in features
        assert features[f]["available"] is False


# ---------------------------------------------------------------------------
# Sanity check on FEATURE_ROUTE_PREFIXES
# ---------------------------------------------------------------------------


def test_feature_route_prefixes_contains_simulation_and_live():
    assert "/trade/simulation" in FEATURE_ROUTE_PREFIXES
    assert "/trade/live" in FEATURE_ROUTE_PREFIXES
    assert FEATURE_ROUTE_PREFIXES["/trade/simulation"] == "simulation"
    assert FEATURE_ROUTE_PREFIXES["/trade/live"] == "live_trading"
