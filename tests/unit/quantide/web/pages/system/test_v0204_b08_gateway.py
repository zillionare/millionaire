"""B08-system-gateway-1: Tests for quantide/web/pages/system/gateway.py.

Target: raise coverage from 53.6% to >=80%.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system.gateway import (
    _build_flash,
    _coerce_gateway_form,
    _compose_gateway_base_url,
    _load_gateway_config,
    _normalize_prefix,
)


# ---------------------------------------------------------------------------
# _normalize_prefix
# ---------------------------------------------------------------------------


def test_normalize_prefix_strips_trailing_slash():
    assert _normalize_prefix("/api/") == "/api"


def test_normalize_prefix_empty_returns_root():
    assert _normalize_prefix("") == "/"


def test_normalize_prefix_already_root():
    assert _normalize_prefix("/") == "/"


def test_normalize_prefix_no_leading_slash():
    """Adds leading slash if missing."""
    assert _normalize_prefix("api") == "/api"


def test_normalize_prefix_complex():
    out = _normalize_prefix("/v1/api")
    assert out == "/v1/api"


# ---------------------------------------------------------------------------
# _compose_gateway_base_url
# ---------------------------------------------------------------------------


def test_compose_gateway_base_url_uses_scheme():
    config = {
        "scheme": "https",
        "server": "example.com",
        "port": 8000,
        "prefix": "/",
    }
    out = _compose_gateway_base_url(config)
    assert "https://" in out
    assert "example.com:8000" in out
    # Note: production strips trailing slash from prefix.


def test_compose_gateway_base_url_with_prefix():
    config = {
        "scheme": "http",
        "server": "127.0.0.1",
        "port": 9000,
        "prefix": "/api/v1",
    }
    out = _compose_gateway_base_url(config)
    # Result format is scheme://server:port/prefix
    assert out.startswith("http://127.0.0.1:9000")
    assert "/api/v1" in out


def test_compose_gateway_base_url_default_port():
    config = {
        "scheme": "http",
        "server": "x",
        "port": 0,
        "prefix": "/",
    }
    out = _compose_gateway_base_url(config)
    assert "http://x:0/" == out or out.startswith("http://x")


# ---------------------------------------------------------------------------
# _coerce_gateway_form
# ---------------------------------------------------------------------------


def test_coerce_gateway_form_basic():
    form = {
        "gateway_enabled": "true",
        "gateway_server": "127.0.0.1",
        "gateway_port": "8000",
        "gateway_api_key": "k",
        "gateway_prefix": "/",
        "gateway_timeout": "10",
    }
    cfg = _coerce_gateway_form(form)
    assert cfg["enabled"] is True
    assert cfg["server"] == "127.0.0.1"
    assert cfg["port"] == 8000
    assert cfg["api_key"] == "k"


def test_coerce_gateway_form_enabled_false():
    form = {
        "gateway_enabled": "false",
        "gateway_server": "",
        "gateway_port": "0",
        "gateway_api_key": "",
        "gateway_prefix": "",
        "gateway_timeout": "10",
    }
    cfg = _coerce_gateway_form(form)
    assert cfg["enabled"] is False
    assert cfg["server"] == ""


def test_coerce_gateway_form_missing_enabled_defaults_false():
    form = {
        "gateway_server": "x", "gateway_port": "8000",
        "gateway_api_key": "k", "gateway_prefix": "/",
        "gateway_timeout": "10",
    }
    cfg = _coerce_gateway_form(form)
    assert cfg["enabled"] is False


# ---------------------------------------------------------------------------
# _build_flash
# ---------------------------------------------------------------------------


def test_build_flash_info():
    flash = _build_flash("hello", "info")
    text = str(flash)
    assert "hello" in text


def test_build_flash_success():
    flash = _build_flash("ok", "success")
    text = str(flash)
    assert "ok" in text


def test_build_flash_warning():
    flash = _build_flash("warn", "warning")
    text = str(flash)
    assert "warn" in text


def test_build_flash_error():
    flash = _build_flash("err", "error")
    text = str(flash)
    assert "err" in text


def test_build_flash_unknown_tone():
    flash = _build_flash("m", "weird-tone")
    text = str(flash)
    assert "m" in text


# ---------------------------------------------------------------------------
# _load_gateway_config
# ---------------------------------------------------------------------------


def test_load_gateway_config_returns_dict():
    cfg = _load_gateway_config()
    assert isinstance(cfg, dict)
    assert "enabled" in cfg
    assert "server" in cfg
    assert "port" in cfg


def test_load_gateway_config_base_url_present():
    cfg = _load_gateway_config()
    assert "base_url" in cfg
