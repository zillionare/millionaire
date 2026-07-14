"""B08-system-gateway: Test small helpers in system/gateway.py."""

from __future__ import annotations

from quantide.web.pages.system.gateway import (
    _compose_gateway_base_url,
    _coerce_gateway_form,
    _normalize_prefix,
)


# ---------------------------------------------------------------------------
# _normalize_prefix
# ---------------------------------------------------------------------------


def test_normalize_prefix_basic():
    assert _normalize_prefix("/foo") == "/foo"


def test_normalize_prefix_strip_trailing_slash():
    assert _normalize_prefix("/foo/") == "/foo"


def test_normalize_prefix_no_leading_slash():
    assert _normalize_prefix("foo") == "/foo"


def test_normalize_prefix_root():
    assert _normalize_prefix("/") == "/"


def test_normalize_prefix_empty_string():
    assert _normalize_prefix("") == "/"


def test_normalize_prefix_none():
    assert _normalize_prefix(None) == "/"


# ---------------------------------------------------------------------------
# _compose_gateway_base_url
# ---------------------------------------------------------------------------


def test_compose_gateway_base_url_no_server():
    assert _compose_gateway_base_url({}) == ""
    assert _compose_gateway_base_url({"server": ""}) == ""


def test_compose_gateway_base_url_default():
    out = _compose_gateway_base_url({"server": "localhost", "port": 8000})
    assert out == "http://localhost:8000"


def test_compose_gateway_base_url_with_scheme():
    out = _compose_gateway_base_url({"server": "x", "port": 1234, "scheme": "https"})
    assert out == "https://x:1234"


def test_compose_gateway_base_url_with_prefix():
    out = _compose_gateway_base_url({"server": "x", "port": 1234, "prefix": "/api"})
    assert out == "http://x:1234/api"


def test_compose_gateway_base_url_default_port():
    """When port is empty, defaults to 8000."""
    out = _compose_gateway_base_url({"server": "x", "port": ""})
    assert out == "http://x:8000"


# ---------------------------------------------------------------------------
# _coerce_gateway_form
# ---------------------------------------------------------------------------


def test_coerce_gateway_form_basic():
    out = _coerce_gateway_form({
        "gateway_enabled": "on",
        "gateway_server": "localhost",
        "gateway_port": "1234",
    })
    assert out["enabled"] is True
    assert out["server"] == "localhost"
    assert out["port"] == 1234
    assert out["scheme"] == "http"
    assert out["timeout"] == 10


def test_coerce_gateway_form_disabled():
    out = _coerce_gateway_form({"gateway_enabled": "off"})
    assert out["enabled"] is False


def test_coerce_gateway_form_strips_whitespace():
    out = _coerce_gateway_form({"gateway_server": "  host  "})
    assert out["server"] == "host"


def test_coerce_gateway_form_default_timeout_one():
    """timeout below 1 clamped to 1."""
    out = _coerce_gateway_form({"gateway_timeout": "0"})
    assert out["timeout"] == 1


def test_coerce_gateway_form_api_key():
    out = _coerce_gateway_form({"gateway_api_key": "secret"})
    assert out["api_key"] == "secret"


def test_coerce_gateway_form_with_prefix():
    out = _coerce_gateway_form({"gateway_prefix": "/api/"})
    assert out["prefix"] == "/api"
