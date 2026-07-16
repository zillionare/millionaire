"""B14-gateway: Coverage tests for quantide/web/pages/system/gateway.py.

Target lines: 72-87 (_load_gateway_config fallback to settings),
112 (non-200 status), 136-138 (generic Exception in _test_gateway_connection),
186 (enabled but no base_url), 201-205 (test_result success branch),
281 (short api key masking), 457-462 (test_connection POST branch),
505-506 (save_config inner fallback pass).
"""

from __future__ import annotations

import urllib.error
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.pages.system import gateway as gw_mod
from quantide.web.pages.system.gateway import (
    _build_config_form,
    _build_connection_status,
    _load_gateway_config,
    _test_gateway_connection,
    save_config as gw_save_config,
    test_connection as gw_test_connection,
)


class _FakeURLResp:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ---------------------------------------------------------------------------
# _load_gateway_config: fallback to settings on exception
# ---------------------------------------------------------------------------


def test_load_gateway_config_db_exception_falls_back_to_settings():
    """db['app_state'].get raises -> except branch -> settings fallback."""
    with patch.object(gw_mod, "db") as mock_db:
        mock_db.__getitem__.return_value.get = MagicMock(side_effect=Exception("boom"))
        out = _load_gateway_config()
    assert "enabled" in out
    assert "base_url" in out
    assert isinstance(out["port"], int)


def test_load_gateway_config_app_state_row_missing_falls_back():
    """db.get returns None -> falls to settings branch."""
    with patch.object(gw_mod, "db") as mock_db:
        mock_db.__getitem__.return_value.get = MagicMock(return_value=None)
        out = _load_gateway_config()
    assert "enabled" in out
    assert "base_url" in out


# ---------------------------------------------------------------------------
# _test_gateway_connection: non-200, URLError, generic Exception
# ---------------------------------------------------------------------------


def test_test_gateway_connection_non_200_returns_http_error():
    """Resp code 500 -> returns success=False with HTTP code."""
    fake_resp = _FakeURLResp(500)
    with patch.object(gw_mod, "urllib") as mock_urllib:
        mock_urllib.request.Request = MagicMock()
        mock_urllib.request.urlopen = MagicMock(return_value=fake_resp)
        out = _test_gateway_connection("http://x", api_key="k", timeout=1)
    assert out["success"] is False
    assert "HTTP 500" in out["error"]


def test_test_gateway_connection_url_error():
    """URLError -> returns success=False with str(reason)."""
    err = urllib.error.URLError("conn refused")
    with patch.object(gw_mod, "urllib") as mock_urllib:
        mock_urllib.request.Request = MagicMock()
        mock_urllib.request.urlopen = MagicMock(side_effect=err)
        # Preserve real exception classes so `except` clauses work.
        mock_urllib.error.HTTPError = urllib.error.HTTPError
        mock_urllib.request.URLError = urllib.error.URLError
        out = _test_gateway_connection("http://x", api_key="k", timeout=1)
    assert out["success"] is False
    assert "conn refused" in out["error"]


def test_test_gateway_connection_generic_exception():
    """Generic Exception -> returns success=False with str(e)."""
    with patch.object(gw_mod, "urllib") as mock_urllib:
        mock_urllib.request.Request = MagicMock(side_effect=ValueError("bad url"))
        mock_urllib.error.HTTPError = urllib.error.HTTPError
        mock_urllib.request.URLError = urllib.error.URLError
        out = _test_gateway_connection("http://x", api_key="k", timeout=1)
    assert out["success"] is False
    assert "bad url" in out["error"]


# ---------------------------------------------------------------------------
# _build_connection_status: enabled but no base_url; success branch
# ---------------------------------------------------------------------------


def test_build_connection_status_enabled_no_base_url():
    """config enabled but base_url empty -> 'gateway address not configured' card."""
    config = {"enabled": True, "base_url": ""}
    out = _build_connection_status(config, test_result=None)
    text = str(out)
    assert "网关地址未配置" in text


def test_build_connection_status_success_branch():
    """test_result success=True -> green styling + '已连接'."""
    config = {
        "enabled": True,
        "base_url": "http://x:8000",
    }
    test_result = {"success": True, "latency_ms": 42, "error": ""}
    out = _build_connection_status(config, test_result=test_result)
    text = str(out)
    assert "已连接" in text
    assert "42" in text


# ---------------------------------------------------------------------------
# _build_config_form: short api key masking (key length <= 4)
# ---------------------------------------------------------------------------


def test_build_config_form_short_api_key_masked():
    """api_key length <= 4 -> masked as all dots."""
    config = {
        "enabled": True,
        "server": "localhost",
        "port": 8000,
        "prefix": "/",
        "api_key": "ab",
        "timeout": 10,
    }
    out = _build_config_form(config)
    assert out is not None


def test_build_config_form_no_api_key():
    """api_key missing -> empty masked_key, placeholder shown."""
    config = {
        "enabled": False,
        "server": "",
        "port": 8000,
        "prefix": "/",
        "api_key": "",
        "timeout": 10,
    }
    out = _build_config_form(config)
    assert out is not None


# ---------------------------------------------------------------------------
# test_connection POST branch with form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_post_with_form_uses_coerce():
    """POST request -> form parsed via _coerce_gateway_form; success path."""
    req = MagicMock()
    req.method = "POST"
    req.form = AsyncMock(return_value={
        "gateway_enabled": "on",
        "gateway_server": "localhost",
        "gateway_port": "8000",
        "gateway_prefix": "/",
        "gateway_api_key": "key123",
        "gateway_timeout": "10",
    })
    test_result = {"success": True, "latency_ms": 5, "error": ""}
    with patch.object(gw_mod, "_test_gateway_connection", return_value=test_result), \
         patch.object(gw_mod, "_render_page", return_value="rendered") as mock_render:
        out = await gw_test_connection(req)
    assert out == "rendered"
    _, kwargs = mock_render.call_args
    # Success message set on success path.
    assert kwargs.get("success_message") == "连通性测试通过"
    assert kwargs.get("test_result") == test_result


@pytest.mark.asyncio
async def test_test_connection_post_failure_path_uses_error_message():
    """POST request with successful coercion but _test_gateway_connection
    returns failure -> render called with error_message."""
    req = MagicMock()
    req.method = "POST"
    req.form = AsyncMock(return_value={
        "gateway_enabled": "on",
        "gateway_server": "localhost",
        "gateway_port": "8000",
        "gateway_prefix": "/",
        "gateway_api_key": "",
        "gateway_timeout": "10",
    })
    test_result = {"success": False, "latency_ms": 1, "error": "down"}
    with patch.object(gw_mod, "_test_gateway_connection", return_value=test_result), \
         patch.object(gw_mod, "_render_page", return_value="rendered") as mock_render:
        out = await gw_test_connection(req)
    assert out == "rendered"
    _, kwargs = mock_render.call_args
    assert kwargs.get("error_message") == "连通性测试失败"


@pytest.mark.asyncio
async def test_test_connection_get_disabled_config_returns_error():
    """GET request with disabled config -> error message 'not enabled'."""
    req = MagicMock()
    req.method = "GET"
    disabled_config = {
        "enabled": False,
        "base_url": "",
        "api_key": "",
        "timeout": 10,
    }
    with patch.object(gw_mod, "_load_gateway_config", return_value=disabled_config), \
         patch.object(gw_mod, "_render_page", return_value="rendered") as mock_render:
        out = await gw_test_connection(req)
    assert out == "rendered"
    _, kwargs = mock_render.call_args
    assert "网关未启用" in kwargs.get("error_message", "")


@pytest.mark.asyncio
async def test_test_connection_post_invalid_port_returns_error():
    """POST with bad port -> ValueError -> fallback render with error message."""
    req = MagicMock()
    req.method = "POST"
    req.form = AsyncMock(return_value={
        "gateway_enabled": "on",
        "gateway_server": "localhost",
        "gateway_port": "not-a-number",
        "gateway_prefix": "/",
        "gateway_api_key": "",
        "gateway_timeout": "10",
    })
    fallback = {"enabled": False, "base_url": ""}
    with patch.object(gw_mod, "_load_gateway_config", return_value=fallback), \
         patch.object(gw_mod, "_render_page", return_value="rendered") as mock_render:
        out = await gw_test_connection(req)
    assert out == "rendered"
    _, kwargs = mock_render.call_args
    assert "参数错误" in kwargs.get("error_message", "")


# ---------------------------------------------------------------------------
# save_config: inner fallback pass branch (form coerce fails in except)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_config_save_failure_with_bad_form_passes_inner_except():
    """init_wizard.save_gateway_config raises, fallback _coerce_gateway_form
    also raises -> inner except pass branch (lines 505-506) executes."""
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "gateway_enabled": "on",
        "gateway_server": "localhost",
        "gateway_port": "not-a-number",  # causes _coerce_gateway_form ValueError
        "gateway_prefix": "/",
        "gateway_api_key": "",
        "gateway_timeout": "10",
    })
    fallback = {"enabled": False, "base_url": ""}
    with patch.object(gw_mod, "_load_gateway_config", return_value=fallback), \
         patch.object(gw_mod, "init_wizard") as mock_iw, \
         patch.object(gw_mod, "_render_page", return_value="rendered"):
        mock_iw.save_gateway_config = MagicMock(side_effect=RuntimeError("db down"))
        out = await gw_save_config(req)
    assert out == "rendered"


@pytest.mark.asyncio
async def test_save_config_save_failure_with_valid_form_updates_fallback():
    """save_gateway_config raises, fallback _coerce_gateway_form succeeds ->
    fallback.update runs (covers happy path of inner try)."""
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "gateway_enabled": "on",
        "gateway_server": "localhost",
        "gateway_port": "8000",
        "gateway_prefix": "/",
        "gateway_api_key": "",
        "gateway_timeout": "10",
    })
    fallback = {"enabled": False, "base_url": ""}
    with patch.object(gw_mod, "_load_gateway_config", return_value=fallback), \
         patch.object(gw_mod, "init_wizard") as mock_iw, \
         patch.object(gw_mod, "_render_page", return_value="rendered"):
        mock_iw.save_gateway_config = MagicMock(side_effect=RuntimeError("db down"))
        out = await gw_save_config(req)
    assert out == "rendered"
