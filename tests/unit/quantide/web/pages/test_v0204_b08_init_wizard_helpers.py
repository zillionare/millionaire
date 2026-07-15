"""B08-init-wizard-helpers: Test small helper functions in init_wizard.py."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.pages import init_wizard as iw_mod
from starlette.responses import RedirectResponse
from quantide.web.pages.init_wizard import (
    _coerce_checkbox,
    _extract_form_updates,
    _format_date_zh,
    _get_download_error,
    _merge_state,
    _normalize_form_values,
    _parse_epoch_input,
    _parse_int_input,
    _parse_positive_int_input,
    _pick_first_value,
    _render_inline_error,
    _request_in_force_mode,
    _set_download_error,
    _set_reconfigure_mode,
    _update_sync_status,
    _with_force_query,
)


# ---------------------------------------------------------------------------
# _format_date_zh
# ---------------------------------------------------------------------------


def test_format_date_zh_date_obj():
    """[AC-NFR1101-01] test_format_date_zh_date_obj."""
    out = _format_date_zh(datetime.date(2024, 6, 15))
    assert "2024" in out and "06" in out and "15" in out


def test_format_date_zh_iso_string():
    """[AC-NFR1101-01] test_format_date_zh_iso_string."""
    out = _format_date_zh("2024-06-15")
    assert "2024" in out


def test_format_date_zh_already_chinese():
    """[AC-NFR1101-01] If input is already in Chinese format, returned as-is."""
    out = _format_date_zh("2024年06月15日")
    assert out == "2024年06月15日"


def test_format_date_zh_empty_string():
    """[AC-NFR1101-01] test_format_date_zh_empty_string."""
    assert _format_date_zh("") == ""


def test_format_date_zh_none():
    """[AC-NFR1101-01] test_format_date_zh_none."""
    assert _format_date_zh(None) == ""


# ---------------------------------------------------------------------------
# _parse_epoch_input
# ---------------------------------------------------------------------------


def test_parse_epoch_input_iso():
    """[AC-NFR1101-01] test_parse_epoch_input_iso."""
    assert _parse_epoch_input("2024-06-15") == datetime.date(2024, 6, 15)


def test_parse_epoch_input_chinese():
    """[AC-NFR1101-01] test_parse_epoch_input_chinese."""
    assert _parse_epoch_input("2024年06月15日") == datetime.date(2024, 6, 15)


def test_parse_epoch_input_slash():
    """[AC-NFR1101-01] test_parse_epoch_input_slash."""
    assert _parse_epoch_input("2024/06/15") == datetime.date(2024, 6, 15)


def test_parse_epoch_input_invalid_raises():
    """[AC-NFR1101-01] test_parse_epoch_input_invalid_raises."""
    with pytest.raises(ValueError):
        _parse_epoch_input("garbage")


def test_parse_epoch_input_empty_raises():
    """[AC-NFR1101-01] test_parse_epoch_input_empty_raises."""
    with pytest.raises(ValueError):
        _parse_epoch_input("")


# ---------------------------------------------------------------------------
# _pick_first_value
# ---------------------------------------------------------------------------


def test_pick_first_value_none():
    """[AC-NFR1101-01] test_pick_first_value_none."""
    assert _pick_first_value(None, ("a", "b"), "default") == "default"


def test_pick_first_value_first_key():
    """[AC-NFR1101-01] test_pick_first_value_first_key."""
    assert _pick_first_value({"a": 1, "b": 2}, ("a", "b"), "default") == 1


def test_pick_first_value_second_key():
    """[AC-NFR1101-01] test_pick_first_value_second_key."""
    assert _pick_first_value({"b": 2}, ("a", "b"), "default") == 2


def test_pick_first_value_missing():
    """[AC-NFR1101-01] test_pick_first_value_missing."""
    assert _pick_first_value({}, ("a", "b"), "default") == "default"


# ---------------------------------------------------------------------------
# _coerce_checkbox
# ---------------------------------------------------------------------------


def test_coerce_checkbox_bool():
    """[AC-NFR1101-01] test_coerce_checkbox_bool."""
    assert _coerce_checkbox(True) is True
    assert _coerce_checkbox(False) is False


def test_coerce_checkbox_none_uses_default():
    """[AC-NFR1101-01] test_coerce_checkbox_none_uses_default."""
    assert _coerce_checkbox(None) is False
    assert _coerce_checkbox(None, default=True) is True


def test_coerce_checkbox_text_truthy():
    """[AC-NFR1101-01] test_coerce_checkbox_text_truthy."""
    assert _coerce_checkbox("on") is True
    assert _coerce_checkbox("yes") is True
    assert _coerce_checkbox("1") is True


def test_coerce_checkbox_text_falsy():
    """[AC-NFR1101-01] test_coerce_checkbox_text_falsy."""
    assert _coerce_checkbox("off") is False
    assert _coerce_checkbox("false") is False
    assert _coerce_checkbox("0") is False


def test_coerce_checkbox_empty_uses_default():
    """[AC-NFR1101-01] test_coerce_checkbox_empty_uses_default."""
    assert _coerce_checkbox("", default=True) is True
    assert _coerce_checkbox("", default=False) is False


# ---------------------------------------------------------------------------
# _normalize_form_values
# ---------------------------------------------------------------------------


def test_normalize_form_values():
    """[AC-NFR1101-01] test_normalize_form_values."""
    aliases = {"x": ("a",), "y": ("b", "c")}
    defaults = {"x": "dx", "y": "dy"}
    out = _normalize_form_values({"a": 1, "c": 3}, aliases, defaults)
    assert out["x"] == 1
    assert out["y"] == 3


def test_normalize_form_values_uses_defaults():
    """[AC-NFR1101-01] test_normalize_form_values_uses_defaults."""
    aliases = {"x": ("a",)}
    defaults = {"x": "dx"}
    out = _normalize_form_values({}, aliases, defaults)
    assert out["x"] == "dx"


def test_normalize_form_values_none_source():
    """[AC-NFR1101-01] test_normalize_form_values_none_source."""
    aliases = {"x": ("a",)}
    defaults = {"x": "dx"}
    out = _normalize_form_values(None, aliases, defaults)
    assert out["x"] == "dx"


# ---------------------------------------------------------------------------
# _extract_form_updates
# ---------------------------------------------------------------------------


def test_extract_form_updates_none():
    """[AC-NFR1101-01] test_extract_form_updates_none."""
    assert _extract_form_updates(None, {"x": ("a",)}) == {}


def test_extract_form_updates_present():
    """[AC-NFR1101-01] test_extract_form_updates_present."""
    out = _extract_form_updates({"a": 1}, {"x": ("a",)})
    assert out == {"x": 1}


def test_extract_form_updates_alternate_alias():
    """[AC-NFR1101-01] test_extract_form_updates_alternate_alias."""
    out = _extract_form_updates({"b": 2}, {"x": ("a", "b")})
    assert out == {"x": 2}


def test_extract_form_updates_missing_key():
    """[AC-NFR1101-01] test_extract_form_updates_missing_key."""
    out = _extract_form_updates({}, {"x": ("a",)})
    assert out == {}


# ---------------------------------------------------------------------------
# _merge_state
# ---------------------------------------------------------------------------


def test_merge_state_merges():
    """[AC-NFR1101-01] test_merge_state_merges."""
    base = {"a": 1, "b": 2}
    updates = {"b": 3, "c": 4}
    out = _merge_state(base, updates)
    assert out == {"a": 1, "b": 3, "c": 4}


def test_merge_state_empty_updates():
    """[AC-NFR1101-01] test_merge_state_empty_updates."""
    base = {"a": 1}
    out = _merge_state(base, {})
    assert out == {"a": 1}


def test_merge_state_empty_base():
    """[AC-NFR1101-01] test_merge_state_empty_base."""
    out = _merge_state({}, {"a": 1})
    assert out == {"a": 1}


# ---------------------------------------------------------------------------
# _parse_int_input
# ---------------------------------------------------------------------------


def test_parse_int_input_valid():
    """[AC-NFR1101-01] test_parse_int_input_valid."""
    assert _parse_int_input("42", "x", 0) == 42


def test_parse_int_input_empty_uses_default():
    """[AC-NFR1101-01] test_parse_int_input_empty_uses_default."""
    assert _parse_int_input("", "x", 99) == 99


def test_parse_int_input_invalid_raises():
    """[AC-NFR1101-01] test_parse_int_input_invalid_raises."""
    with pytest.raises(ValueError, match="整数"):
        _parse_int_input("not-int", "x", 0)


def test_parse_int_input_int_passes_through():
    """[AC-NFR1101-01] test_parse_int_input_int_passes_through."""
    assert _parse_int_input(7, "x", 0) == 7


# ---------------------------------------------------------------------------
# _parse_positive_int_input
# ---------------------------------------------------------------------------


def test_parse_positive_int_input():
    """[AC-NFR1101-01] test_parse_positive_int_input."""
    assert _parse_positive_int_input("42", "x", 1) == 42


def test_parse_positive_int_input_zero_clamped_to_one():
    """[AC-NFR1101-01] 0 parses as 0, but max(1, 0) returns 1."""
    assert _parse_positive_int_input("0", "x", 1) == 1


def test_parse_positive_int_input_negative_clamped():
    """[AC-NFR1101-01] test_parse_positive_int_input_negative_clamped."""
    assert _parse_positive_int_input("-5", "x", 1) == 1


def test_parse_positive_int_input_default():
    """[AC-NFR1101-01] test_parse_positive_int_input_default."""
    assert _parse_positive_int_input("", "x", 99) == 99


# ---------------------------------------------------------------------------
# _render_inline_error
# ---------------------------------------------------------------------------


def test_render_inline_error():
    """[AC-NFR1101-01] test_render_inline_error."""
    out = _render_inline_error("Something broke")
    assert out is not None


# ---------------------------------------------------------------------------
# _set_download_error / _get_download_error
# ---------------------------------------------------------------------------


def test_set_download_error_then_get():
    """[AC-NFR1101-01] test_set_download_error_then_get."""
    iw_mod._download_error_message = None
    _set_download_error("boom")
    assert iw_mod._download_error_message == "boom"


def test_set_download_error_empty_clears():
    """[AC-NFR1101-01] test_set_download_error_empty_clears."""
    iw_mod._download_error_message = "old"
    _set_download_error("")
    assert iw_mod._download_error_message is None


def test_set_download_error_strips_whitespace():
    """[AC-NFR1101-01] test_set_download_error_strips_whitespace."""
    iw_mod._download_error_message = None
    _set_download_error("  boom  ")
    assert iw_mod._download_error_message == "boom"


def test_get_download_error_step5_uses_global():
    """[AC-NFR1101-01] test_get_download_error_step5_uses_global."""
    iw_mod._download_error_message = "global-msg"
    got = _get_download_error(step=5)
    assert got == "global-msg"


def test_get_download_error_step_not_5():
    """[AC-NFR1101-01] test_get_download_error_step_not_5."""
    iw_mod._download_error_message = "global-msg"
    got = _get_download_error(step=1)
    assert got is None


def test_get_download_error_explicit_overrides():
    """[AC-NFR1101-01] test_get_download_error_explicit_overrides."""
    got = _get_download_error(step=1, explicit_error="explicit")
    assert got == "explicit"


# ---------------------------------------------------------------------------
# _set_reconfigure_mode / _request_in_force_mode / _with_force_query
# ---------------------------------------------------------------------------


def test_set_reconfigure_mode():
    """[AC-NFR1101-01] test_set_reconfigure_mode."""
    iw_mod._reconfigure_mode_active = False
    _set_reconfigure_mode(True)
    assert iw_mod._reconfigure_mode_active is True
    _set_reconfigure_mode(False)
    assert iw_mod._reconfigure_mode_active is False


def test_request_in_force_mode_true():
    """[AC-NFR1101-01] test_request_in_force_mode_true."""
    req = MagicMock()
    req.query_params = {"force": "true"}
    assert _request_in_force_mode(req) is True


def test_request_in_force_mode_false():
    """[AC-NFR1101-01] test_request_in_force_mode_false."""
    req = MagicMock()
    req.query_params = {"force": "false"}
    assert _request_in_force_mode(req) is False


def test_request_in_force_mode_no_force():
    """[AC-NFR1101-01] test_request_in_force_mode_no_force."""
    req = MagicMock()
    req.query_params = {}
    assert _request_in_force_mode(req) is False


def test_with_force_query_not_in_reconfigure():
    """[AC-NFR1101-01] test_with_force_query_not_in_reconfigure."""
    iw_mod._reconfigure_mode_active = False
    out = _with_force_query("/path")
    assert out == "/path"


def test_with_force_query_in_reconfigure_no_q():
    """[AC-NFR1101-01] test_with_force_query_in_reconfigure_no_q."""
    iw_mod._reconfigure_mode_active = True
    out = _with_force_query("/path")
    assert "force=true" in out
    assert out == "/path?force=true"


def test_with_force_query_in_reconfigure_with_q():
    """[AC-NFR1101-01] test_with_force_query_in_reconfigure_with_q."""
    iw_mod._reconfigure_mode_active = True
    out = _with_force_query("/path?x=1")
    assert out == "/path?x=1&force=true"


# ---------------------------------------------------------------------------
# _update_sync_status
# ---------------------------------------------------------------------------


def test_update_sync_status_sets_progress():
    """[AC-NFR1101-01] test_update_sync_status_sets_progress."""
    _update_sync_status(50, "mid", "half way", completed=False, error=None)
    assert iw_mod._sync_status["progress"] == 50
    assert iw_mod._sync_status["stage"] == "mid"
    assert iw_mod._sync_status["message"] == "half way"
    assert iw_mod._sync_status["completed"] is False
    assert iw_mod._sync_status["error"] is None


def test_update_sync_status_no_message_uses_stage():
    """[AC-NFR1101-01] test_update_sync_status_no_message_uses_stage."""
    _update_sync_status(0, "start", message=None)
    assert iw_mod._sync_status["message"] == "start"


# ---------------------------------------------------------------------------
# _runtime_form_state / _gateway_form_state / _data_init_form_state
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import (
    _data_init_form_state,
    _gateway_form_state,
    _runtime_form_state,
)
from quantide.web.pages import init_wizard as iw_mod_alias


def test_runtime_form_state_default():
    """[AC-NFR1101-01] test_runtime_form_state_default."""
    out = _runtime_form_state()
    assert isinstance(out, dict)
    assert "app_host" in out or "host" in out


def test_runtime_form_state_with_source():
    """[AC-NFR1101-01] test_runtime_form_state_with_source."""
    out = _runtime_form_state({"app_host": "0.0.0.0"})
    assert out["app_host"] == "0.0.0.0"


def test_runtime_form_state_localhost_only():
    """[AC-NFR1101-01] test_runtime_form_state_localhost_only."""
    out = _runtime_form_state({"app_host": "127.0.0.1"})
    # When host is 127.0.0.1, localhost_only should be True
    assert out.get("localhost_only") is True or out.get("app_localhost_only") is True


def test_gateway_form_state_default():
    """[AC-NFR1101-01] test_gateway_form_state_default."""
    out = _gateway_form_state()
    assert isinstance(out, dict)


def test_gateway_form_state_checkbox_enabled():
    """[AC-NFR1101-01] test_gateway_form_state_checkbox_enabled."""
    out = _gateway_form_state({"gateway_enabled": "on"})
    assert out.get("gateway_enabled") is True


def test_gateway_form_state_checkbox_disabled():
    """[AC-NFR1101-01] test_gateway_form_state_checkbox_disabled."""
    out = _gateway_form_state({"gateway_enabled": "off"})
    assert out.get("gateway_enabled") is False


def test_data_init_form_state_default():
    """[AC-NFR1101-01] test_data_init_form_state_default."""
    out = _data_init_form_state()
    assert isinstance(out, dict)


def test_data_init_form_state_with_source():
    """[AC-NFR1101-01] test_data_init_form_state_with_source."""
    out = _data_init_form_state({"epoch": "2020-01-01"})
    assert out["epoch"] == "2020-01-01"


# ---------------------------------------------------------------------------
# _wizard_step_meta + _get_step_meta
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import (
    _get_step_meta,
    _wizard_step_meta,
)


def test_wizard_step_meta_has_all_steps():
    """[AC-NFR1101-01] _wizard_step_meta returns dict for steps 1-6."""
    meta = _wizard_step_meta()
    assert len(meta) == 6
    for i in (1, 2, 3, 4, 5, 6):
        assert i in meta
        assert "title" in meta[i]
        assert "description" in meta[i]


def test_get_step_meta_returns_meta_for_known_steps():
    """[AC-NFR1101-01] test_get_step_meta_returns_meta_for_known_steps."""
    for s in (1, 2, 3, 4, 5, 6):
        meta = _get_step_meta(s)
        assert "title" in meta
        assert "description" in meta


def test_get_step_meta_unknown_falls_back_to_step1():
    """[AC-NFR1101-01] test_get_step_meta_unknown_falls_back_to_step1."""
    meta = _get_step_meta(99)
    assert "title" in meta


# ---------------------------------------------------------------------------
# _check_password_strength
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import _check_password_strength


def test_password_too_short():
    """[AC-NFR1101-01] test_password_too_short."""
    strength, msg = _check_password_strength("aB1!")
    assert strength == "weak"
    assert "8" in msg or "长度" in msg


def test_password_strong():
    """[AC-NFR1101-01] All 4 categories + length >= 10 → strong."""
    strength, msg = _check_password_strength("Abcdef1!@#$%")
    assert strength == "strong"
    assert "强" in msg


def test_password_medium():
    """[AC-NFR1101-01] Exactly 3 of 4 categories, length 8-9 → medium."""
    strength, msg = _check_password_strength("Abcdefgh1")  # 9 chars: lower+upper+digit
    assert strength == "medium"


def test_password_weak_no_categories():
    """[AC-NFR1101-01] Only one category (just letters of one case)."""
    strength, msg = _check_password_strength("aaaaaaaa")
    assert strength == "weak"


def test_password_strong_no_special():
    """[AC-NFR1101-01] lower+upper+digit + length >= 10 → 3 categories, medium."""
    strength, msg = _check_password_strength("Abcdefghi1")
    assert strength == "medium"


def test_password_strong_with_8_chars_no_extra_categories():
    """[AC-NFR1101-01] 8 chars, only one category → weak."""
    strength, msg = _check_password_strength("aaaaaaaa")
    assert strength == "weak"


# ---------------------------------------------------------------------------
# _calculate_download_range + _render_download_range_info
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import (
    _calculate_download_range,
    _render_download_range_info,
)


def test_calculate_download_range_one_year():
    """[AC-NFR1101-01] test_calculate_download_range_one_year."""
    start, end = _calculate_download_range(1)
    today = __import__("datetime").date.today()
    assert end == today
    # ~365 days difference (allow +/-1 day for leap second)
    diff = (today - start).days
    assert 364 <= diff <= 366


def test_calculate_download_range_three_years():
    """[AC-NFR1101-01] test_calculate_download_range_three_years."""
    start, end = _calculate_download_range(3)
    today = __import__("datetime").date.today()
    assert end == today
    diff = (today - start).days
    assert 1094 <= diff <= 1097


def test_calculate_download_range_zero_years():
    """[AC-NFR1101-01] test_calculate_download_range_zero_years."""
    start, end = _calculate_download_range(0)
    assert start == end


def test_render_download_range_info():
    """[AC-NFR1101-01] test_render_download_range_info."""
    out = _render_download_range_info(3)
    assert out is not None


# ---------------------------------------------------------------------------
# handle_complete + SyncProgressDialog + reset_initialization
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import (
    SyncProgressDialog,
    handle_complete,
    reset_initialization,
)


@pytest.mark.asyncio
async def test_handle_complete_success():
    """handle_complete → returns script with redirect."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_bootstrap_runtime_for_initialized_app"), \
         patch.object(iw_mod, "_set_reconfigure_mode"):
        mock_iw.complete_initialization = MagicMock()
        mock_iw.get_completion_redirect = MagicMock(return_value="/dashboard")
        req = MagicMock()
        req.app = MagicMock()
        resp = await handle_complete(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_handle_complete_exception():
    """When init_wizard raises, returns error div."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_bootstrap_runtime_for_initialized_app"), \
         patch.object(iw_mod, "_set_reconfigure_mode"):
        mock_iw.complete_initialization = MagicMock(side_effect=Exception("boom"))
        req = MagicMock()
        req.app = MagicMock()
        resp = await handle_complete(req)
    assert resp is not None


def test_reset_initialization():
    """[AC-NFR1101-01] reset_initialization just calls init_wizard.reset_initialization."""
    import asyncio
    with patch.object(iw_mod, "init_wizard") as mock_iw:
        mock_iw.reset_initialization = AsyncMock()
        asyncio.run(reset_initialization())
    mock_iw.reset_initialization.assert_called_once()


def test_sync_progress_dialog():
    """[AC-NFR1101-01] test_sync_progress_dialog."""
    out = SyncProgressDialog()
    assert out is not None


# ---------------------------------------------------------------------------
# handle_step nav=prev path
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import (
    InitWizardPage,
    get as init_get,
    handle_step,
)


@pytest.mark.asyncio
async def test_init_get_when_already_initialized():
    """When is_initialized()=True, redirect to /."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False):
        mock_iw.is_initialized = MagicMock(return_value=True)
        req = MagicMock()
        req.query_params = {}
        resp = await init_get(req)
    assert isinstance(resp, RedirectResponse)


@pytest.mark.asyncio
async def test_init_get_when_check_raises():
    """When is_initialized raises RuntimeError, continues to render."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False):
        mock_iw.is_initialized = MagicMock(side_effect=RuntimeError("init failed"))
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.start_initialization = MagicMock()
        req = MagicMock()
        req.query_params = {}
        resp = await init_get(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_init_get_when_start_initialization_raises():
    """When start_initialization raises RuntimeError, continues."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False):
        mock_iw.is_initialized = MagicMock(return_value=False)
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.start_initialization = MagicMock(side_effect=RuntimeError("start failed"))
        req = MagicMock()
        req.query_params = {}
        resp = await init_get(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_init_get_force_mode():
    """When force mode, doesn't check is_initialized."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=True):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.start_initialization = MagicMock()
        req = MagicMock()
        req.query_params = {"force": "true"}
        resp = await init_get(req)
    mock_iw.is_initialized.assert_not_called()


@pytest.mark.asyncio
async def test_handle_step_prev_no_action():
    """nav=prev skips data validation."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={"nav": "prev"})
        # Just exercise the path
        resp = await handle_step(req, step=2)
    # No save_runtime_config call expected
    mock_iw.save_runtime_config.assert_not_called()


# ---------------------------------------------------------------------------
# gateway_test
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import gateway_test


@pytest.mark.asyncio
async def test_gateway_test_disabled():
    """When gateway_enabled is False → return info Div."""
    with patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_gateway_form_state", return_value={"gateway_enabled": False, "gateway_server": "x", "gateway_port": 8000, "gateway_prefix": "/", "gateway_api_key": ""}), \
         patch.object(iw_mod, "_extract_form_updates", return_value={}):
        req = MagicMock()
        req.form = AsyncMock(return_value={})
        resp = await gateway_test(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_handle_update_download_range_valid():
    """Updates download range info with valid years."""
    with patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False):
        req = MagicMock()
        req.form = AsyncMock(return_value={"history_years": "3"})
        resp = await iw_mod.handle_update_download_range(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_handle_update_download_range_invalid():
    """Bad input falls back to years=1."""
    with patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False):
        req = MagicMock()
        req.form = AsyncMock(return_value={"history_years": "garbage"})
        resp = await iw_mod.handle_update_download_range(req)
    assert resp is not None


# ---------------------------------------------------------------------------
# handle_step step=3 (admin password)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_step_admin_password_mismatch():
    """step=3 + password mismatch → return error wizard main content."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step3_Admin", return_value="form") as mock_step:
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={"k": "v"})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={"nav": "next", "_current_step": "3",
                                              "admin_password": "abc",
                                              "admin_password_confirm": "xyz"})
        resp = await handle_step(req, step=3)
    assert resp == "err"
    mock_render.assert_called_once()
    # Just confirm render was called (error path taken)
    assert mock_render.called


@pytest.mark.asyncio
async def test_handle_step_admin_password_save_exception():
    """step=3 + save raises → return error wizard main content."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step3_Admin", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={"k": "v"})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.save_admin_password = MagicMock(side_effect=Exception("save failed"))
        req = MagicMock()
        req.form = AsyncMock(return_value={"nav": "next", "_current_step": "3",
                                              "admin_password": "abcdefgh",
                                              "admin_password_confirm": "abcdefgh"})
        resp = await handle_step(req, step=3)
    assert resp == "err"
    assert mock_render.called
