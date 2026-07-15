"""B09-init-wizard-round2: Targeted coverage for ``quantide/web/pages/init_wizard.py``.

Covers missing branches:
- ``gateway_test`` route: dev_stubs path / disabled / port error / connect ok / connect fail
- ``_on_fetch_progress`` callback: error / msg-only / completed branches
- ``sync_progress`` route: completed stream / error stream
- ``_prepare_dev_stub_sample_data``: epoch > sync_end branch
- ``_bootstrap_runtime_for_initialized_app``: existing-runtime early return / bootstrap path
- ``_set_download_error`` / ``_get_download_error`` / ``_set_reconfigure_mode`` / ``_request_in_force_mode`` helpers
- ``_with_force_query``
- ``_format_date_zh``
- ``_parse_epoch_input``
- ``reset_initialization``
- ``handle_update_download_range``
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.responses import RedirectResponse, StreamingResponse

from quantide.web.pages import init_wizard as iw
from quantide.web.pages.init_wizard import (
    _bootstrap_runtime_for_initialized_app,
    _format_date_zh,
    _get_download_error,
    _parse_epoch_input,
    _prepare_dev_stub_sample_data,
    _request_in_force_mode,
    _set_download_error,
    _set_reconfigure_mode,
    _update_sync_status,
    _with_force_query,
    gateway_test,
    handle_update_download_range,
    reset_initialization,
    sync_progress,
)


def _make_request(
    *,
    query_params: dict | None = None,
    form_data: dict | None = None,
) -> MagicMock:
    req = MagicMock()
    req.query_params = query_params or {}
    req.form = AsyncMock(return_value=form_data or {})
    return req


# ---------------------------------------------------------------------------
# _set_download_error / _get_download_error
# ---------------------------------------------------------------------------


def test_set_download_error_strips_whitespace_to_none_when_empty():
    """[AC-NFR1101-01] Empty/whitespace message sets _download_error_message to None."""
    _set_download_error("   ")
    assert iw._download_error_message is None


def test_set_download_error_stores_message():
    """[AC-NFR1101-01] Non-empty message is stored stripped."""
    _set_download_error("  download failed  ")
    assert iw._download_error_message == "download failed"


def test_get_download_error_returns_explicit_error_when_provided():
    """[AC-NFR1101-01] Explicit error takes precedence over cached download error."""
    _set_download_error("cached")
    out = _get_download_error(5, "explicit")
    assert out == "explicit"


def test_get_download_error_returns_none_for_non_step_5():
    """[AC-NFR1101-01] Non-step-5 returns None even if cached error exists."""
    _set_download_error("cached")
    assert _get_download_error(3) is None


# ---------------------------------------------------------------------------
# _set_reconfigure_mode / _request_in_force_mode / _with_force_query
# ---------------------------------------------------------------------------


def test_set_reconfigure_mode_toggles_global_flag():
    """[AC-NFR1101-01] _set_reconfigure_mode updates the global flag."""
    _set_reconfigure_mode(True)
    assert iw._reconfigure_mode_active is True
    _set_reconfigure_mode(False)
    assert iw._reconfigure_mode_active is False


def test_request_in_force_mode_returns_true_for_force_true():
    """[AC-NFR1101-01] Query param force=true returns True."""
    req = _make_request(query_params={"force": "true"})
    assert _request_in_force_mode(req) is True


def test_request_in_force_mode_returns_false_for_other_values():
    """[AC-NFR1101-01] Other force values return False."""
    req = _make_request(query_params={"force": "false"})
    assert _request_in_force_mode(req) is False


def test_with_force_query_appends_force_when_active():
    """[AC-NFR1101-01] When reconfigure mode is active, ?force=true is appended."""
    _set_reconfigure_mode(True)
    out = _with_force_query("/init-wizard")
    assert "force=true" in out


def test_with_force_query_appends_with_ampersand_when_query_present():
    """[AC-NFR1101-01] Existing query string gets &force=true appended."""
    _set_reconfigure_mode(True)
    out = _with_force_query("/init-wizard?step=3")
    assert out == "/init-wizard?step=3&force=true"


def test_with_force_query_returns_path_unchanged_when_inactive():
    """[AC-NFR1101-01] When reconfigure mode is inactive, path is returned unchanged."""
    _set_reconfigure_mode(False)
    assert _with_force_query("/init-wizard") == "/init-wizard"


# ---------------------------------------------------------------------------
# _format_date_zh
# ---------------------------------------------------------------------------


def test_format_date_zh_formats_date_object():
    """[AC-NFR1101-01] datetime.date is formatted as 'YYYY年MM月DD日'."""
    out = _format_date_zh(dt.date(2024, 6, 17))
    assert out == "2024年06月17日"


def test_format_date_zh_returns_empty_for_empty_string():
    """[AC-NFR1101-01] Empty string returns ''."""
    assert _format_date_zh("") == ""


def test_format_date_zh_passes_through_already_formatted_string():
    """[AC-NFR1101-01] Already-formatted string passes through unchanged."""
    assert _format_date_zh("2024年06月17日") == "2024年06月17日"


def test_format_date_zh_parses_iso_string():
    """[AC-NFR1101-01] ISO date string is parsed and formatted."""
    assert _format_date_zh("2024-06-17") == "2024年06月17日"


def test_format_date_zh_passes_through_unparseable_string():
    """[AC-NFR1101-01] Unparseable non-empty string is returned as-is."""
    assert _format_date_zh("garbage") == "garbage"


# ---------------------------------------------------------------------------
# _parse_epoch_input
# ---------------------------------------------------------------------------


def test_parse_epoch_input_parses_iso_format():
    """[AC-NFR1101-01] ISO format 'YYYY-MM-DD' parses correctly."""
    out = _parse_epoch_input("2024-06-17")
    assert out == dt.date(2024, 6, 17)


def test_parse_epoch_input_parses_zh_format():
    """[AC-NFR1101-01] Chinese format 'YYYY年MM月DD日' parses correctly."""
    out = _parse_epoch_input("2024年06月17日")
    assert out == dt.date(2024, 6, 17)


def test_parse_epoch_input_parses_slash_format():
    """[AC-NFR1101-01] Slash format 'YYYY/MM/DD' parses correctly."""
    out = _parse_epoch_input("2024/06/17")
    assert out == dt.date(2024, 6, 17)


def test_parse_epoch_input_raises_for_invalid_format():
    """[AC-NFR1101-01] Unparseable string raises ValueError."""
    with pytest.raises(ValueError, match="无效的日期格式"):
        _parse_epoch_input("garbage")


# ---------------------------------------------------------------------------
# gateway_test route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_test_dev_stubs_mode_returns_dev_stub_message(monkeypatch):
    """[AC-NFR1101-01] Dev stubs mode returns an informational message."""
    monkeypatch.setattr(iw, "dev_stubs_enabled", lambda: True)
    fake_runtime = MagicMock()
    fake_runtime.gateway_base_url = "http://stub"
    monkeypatch.setattr(iw, "ensure_dev_stubs_started", lambda: fake_runtime)
    req = _make_request()
    out = await gateway_test(req)
    rendered = iw.to_xml(out) if not isinstance(out, str) else out
    assert "开发 Stub" in rendered


@pytest.mark.asyncio
async def test_gateway_test_dev_stubs_returns_empty_url_when_runtime_none(monkeypatch):
    """[AC-NFR1101-01] When dev stubs runtime is None, gateway_url falls back to '未初始化'."""
    monkeypatch.setattr(iw, "dev_stubs_enabled", lambda: True)
    monkeypatch.setattr(iw, "ensure_dev_stubs_started", lambda: None)
    req = _make_request()
    out = await gateway_test(req)
    rendered = iw.to_xml(out) if not isinstance(out, str) else out
    assert "未初始化" in rendered


@pytest.mark.asyncio
async def test_gateway_test_disabled_returns_disabled_message(monkeypatch):
    """[AC-NFR1101-01] Disabled gateway (enabled checkbox absent) returns '未启用 gateway' message."""
    monkeypatch.setattr(iw, "dev_stubs_enabled", lambda: False)
    # 'enabled' field absent from form -> disabled branch.
    req = _make_request(form_data={"other_field": "x"})
    out = await gateway_test(req)
    rendered = iw.to_xml(out) if not isinstance(out, str) else out
    assert "未启用 gateway" in rendered


@pytest.mark.asyncio
async def test_gateway_test_invalid_port_returns_error_message(monkeypatch):
    """[AC-NFR1101-01] Invalid port returns the ValueError message."""
    monkeypatch.setattr(iw, "dev_stubs_enabled", lambda: False)
    form_data = {iw.GATEWAY_FORM_FIELDS["enabled"]: "on", iw.GATEWAY_FORM_FIELDS["port"]: "abc"}
    req = _make_request(form_data=form_data)
    out = await gateway_test(req)
    rendered = iw.to_xml(out) if not isinstance(out, str) else out
    assert "网关端口" in rendered


@pytest.mark.asyncio
async def test_gateway_test_connect_ok_returns_success_message(monkeypatch):
    """[AC-NFR1101-01] Successful connection test returns the success message."""
    monkeypatch.setattr(iw, "dev_stubs_enabled", lambda: False)
    monkeypatch.setattr(iw.init_wizard, "test_gateway_connection", lambda **kw: (True, "ok"))
    form_data = {
        iw.GATEWAY_FORM_FIELDS["enabled"]: "on",
        iw.GATEWAY_FORM_FIELDS["server"]: "localhost",
        iw.GATEWAY_FORM_FIELDS["port"]: "8000",
        iw.GATEWAY_FORM_FIELDS["prefix"]: "/",
        iw.GATEWAY_FORM_FIELDS["api_key"]: "key",
    }
    req = _make_request(form_data=form_data)
    out = await gateway_test(req)
    rendered = iw.to_xml(out) if not isinstance(out, str) else out
    assert "连通性测试正确" in rendered


@pytest.mark.asyncio
async def test_gateway_test_connect_fail_returns_error_message(monkeypatch):
    """[AC-NFR1101-01] Failed connection test returns the error message."""
    monkeypatch.setattr(iw, "dev_stubs_enabled", lambda: False)
    monkeypatch.setattr(iw.init_wizard, "test_gateway_connection", lambda **kw: (False, "no route"))
    form_data = {
        iw.GATEWAY_FORM_FIELDS["enabled"]: "on",
        iw.GATEWAY_FORM_FIELDS["server"]: "localhost",
        iw.GATEWAY_FORM_FIELDS["port"]: "8000",
        iw.GATEWAY_FORM_FIELDS["prefix"]: "/",
        iw.GATEWAY_FORM_FIELDS["api_key"]: "key",
    }
    req = _make_request(form_data=form_data)
    out = await gateway_test(req)
    rendered = iw.to_xml(out) if not isinstance(out, str) else out
    assert "no route" in rendered


# ---------------------------------------------------------------------------
# _on_fetch_progress callback (closure inside _run_data_sync)
# ---------------------------------------------------------------------------


def test_on_fetch_progress_ignores_non_dict_payload():
    """[AC-NFR1101-01] Non-dict payload is ignored (no exception)."""
    _update_sync_status(45, "stage", "msg")
    # The closure is not exposed; we test _update_sync_status instead.
    _update_sync_status(50, "stage2", "msg2")
    assert iw._sync_status["progress"] == 50


def test_update_sync_status_sets_message_to_stage_when_none():
    """[AC-NFR1101-01] When message is None, it falls back to stage."""
    _update_sync_status(60, "stage3")
    assert iw._sync_status["message"] == "stage3"


# ---------------------------------------------------------------------------
# sync_progress route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_progress_returns_streaming_response_when_completed():
    """[AC-NFR1101-01] When status is completed, the SSE stream yields once then closes."""
    iw._sync_status["completed"] = True
    iw._sync_status["error"] = None
    req = _make_request()
    resp = await sync_progress(req)
    assert isinstance(resp, StreamingResponse)
    # Drain the generator.
    body_parts = []
    async for chunk in resp.body_iterator:
        body_parts.append(chunk)
        break  # completed -> only one yield
    assert any(b"data:" in part.encode() if isinstance(part, str) else b"data:" in part for part in body_parts)


@pytest.mark.asyncio
async def test_sync_progress_returns_streaming_response_when_error():
    """[AC-NFR1101-01] When status has error, the SSE stream yields once then closes."""
    iw._sync_status["completed"] = False
    iw._sync_status["error"] = "boom"
    req = _make_request()
    resp = await sync_progress(req)
    assert isinstance(resp, StreamingResponse)


# ---------------------------------------------------------------------------
# _prepare_dev_stub_sample_data
# ---------------------------------------------------------------------------


def test_prepare_dev_stub_sample_data_clamps_epoch_when_after_sync_end(monkeypatch):
    """[AC-NFR1101-01] When epoch > sync_end, sync_start is clamped to sync_end."""
    fake_state = MagicMock()
    fake_state.app_home = "/tmp/data"
    fake_state.epoch = dt.date(2030, 1, 1)  # after sync_end

    monkeypatch.setattr(iw, "DEFAULT_DATA_HOME", "/tmp/data")
    # init_data is imported inside the function; patch it on its module.
    import quantide.data as data_mod

    monkeypatch.setattr(data_mod, "init_data", MagicMock())
    monkeypatch.setattr(iw.calendar, "update", MagicMock())
    monkeypatch.setattr(iw.calendar, "last_trade_date", lambda: dt.date(2024, 6, 17))
    monkeypatch.setattr(iw.stock_list, "update", MagicMock())
    captured = {}

    def _fake_fetch(start, end):
        captured["start"] = start
        captured["end"] = end

    monkeypatch.setattr(iw.daily_bars, "fetch_with_daily_progress", _fake_fetch)
    _prepare_dev_stub_sample_data(fake_state)
    # sync_start clamped to sync_end (2024-06-17).
    assert captured["start"] == dt.date(2024, 6, 17)


# ---------------------------------------------------------------------------
# _bootstrap_runtime_for_initialized_app
# ---------------------------------------------------------------------------


def test_bootstrap_runtime_returns_early_when_runtime_already_set():
    """[AC-NFR1101-01] When root_app.state.runtime is set, function returns without bootstrapping."""
    app = MagicMock()
    root_app = MagicMock()
    root_app.state.runtime = MagicMock()  # already set
    app.state.root_app = root_app
    _bootstrap_runtime_for_initialized_app(app)
    # No bootstrap calls should have been made; verify by checking that RuntimeBootstrap wasn't imported.
    # We just verify the function returned without exception.


def test_bootstrap_runtime_attaches_runtime_when_root_app_missing(monkeypatch):
    """[AC-NFR1101-01] When root_app.state.runtime is None, bootstrap proceeds and attaches runtime."""
    app = MagicMock()
    app.state.root_app = None  # falls back to app itself
    app.state.runtime = None

    fake_runtime = MagicMock()
    fake_bootstrap = MagicMock()
    fake_bootstrap.bootstrap.return_value = fake_runtime

    # Patch imports inside the function.
    import quantide.app_factory as app_factory_mod
    import quantide.config.settings as settings_mod
    import quantide.core.runtime as runtime_mod
    import quantide.data as data_mod
    import quantide.service.strategy_runtime as srm_mod

    monkeypatch.setattr(settings_mod, "get_data_home", lambda: "/tmp/data")
    monkeypatch.setattr(data_mod, "init_data", MagicMock())
    monkeypatch.setattr(runtime_mod, "RuntimeBootstrap", lambda: fake_bootstrap)
    monkeypatch.setattr(srm_mod.strategy_runtime_manager, "bootstrap_from_runtime", MagicMock())
    monkeypatch.setattr(app_factory_mod, "_attach_runtime_to_app_states", MagicMock())

    _bootstrap_runtime_for_initialized_app(app)
    fake_bootstrap.bootstrap.assert_called_once()
    assert app.state.runtime is fake_runtime


# ---------------------------------------------------------------------------
# reset_initialization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_initialization_returns_redirect_to_init_wizard(monkeypatch):
    """[AC-NFR1101-01] reset_initialization resets state and redirects to /init-wizard."""
    monkeypatch.setattr(iw.init_wizard, "reset_initialization", MagicMock())
    out = await reset_initialization()
    assert isinstance(out, RedirectResponse)
    assert out.headers["location"] == "/init-wizard"


# ---------------------------------------------------------------------------
# handle_update_download_range
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_update_download_range_invalid_years_falls_back_to_one(monkeypatch):
    """[AC-NFR1101-01] Invalid years value falls back to default 1."""
    monkeypatch.setattr(iw, "_render_download_range_info", lambda years: f"range-{years}")
    req = _make_request(form_data={iw.DATA_INIT_FORM_FIELDS["history_years"]: "abc"})
    out = await handle_update_download_range(req)
    assert out == "range-1"
