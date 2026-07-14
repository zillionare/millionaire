"""B08-init-wizard-helpers: Test small helper functions in init_wizard.py."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.pages import init_wizard as iw_mod
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
    out = _format_date_zh(datetime.date(2024, 6, 15))
    assert "2024" in out and "06" in out and "15" in out


def test_format_date_zh_iso_string():
    out = _format_date_zh("2024-06-15")
    assert "2024" in out


def test_format_date_zh_already_chinese():
    """If input is already in Chinese format, returned as-is."""
    out = _format_date_zh("2024年06月15日")
    assert out == "2024年06月15日"


def test_format_date_zh_empty_string():
    assert _format_date_zh("") == ""


def test_format_date_zh_none():
    assert _format_date_zh(None) == ""


# ---------------------------------------------------------------------------
# _parse_epoch_input
# ---------------------------------------------------------------------------


def test_parse_epoch_input_iso():
    assert _parse_epoch_input("2024-06-15") == datetime.date(2024, 6, 15)


def test_parse_epoch_input_chinese():
    assert _parse_epoch_input("2024年06月15日") == datetime.date(2024, 6, 15)


def test_parse_epoch_input_slash():
    assert _parse_epoch_input("2024/06/15") == datetime.date(2024, 6, 15)


def test_parse_epoch_input_invalid_raises():
    with pytest.raises(ValueError):
        _parse_epoch_input("garbage")


def test_parse_epoch_input_empty_raises():
    with pytest.raises(ValueError):
        _parse_epoch_input("")


# ---------------------------------------------------------------------------
# _pick_first_value
# ---------------------------------------------------------------------------


def test_pick_first_value_none():
    assert _pick_first_value(None, ("a", "b"), "default") == "default"


def test_pick_first_value_first_key():
    assert _pick_first_value({"a": 1, "b": 2}, ("a", "b"), "default") == 1


def test_pick_first_value_second_key():
    assert _pick_first_value({"b": 2}, ("a", "b"), "default") == 2


def test_pick_first_value_missing():
    assert _pick_first_value({}, ("a", "b"), "default") == "default"


# ---------------------------------------------------------------------------
# _coerce_checkbox
# ---------------------------------------------------------------------------


def test_coerce_checkbox_bool():
    assert _coerce_checkbox(True) is True
    assert _coerce_checkbox(False) is False


def test_coerce_checkbox_none_uses_default():
    assert _coerce_checkbox(None) is False
    assert _coerce_checkbox(None, default=True) is True


def test_coerce_checkbox_text_truthy():
    assert _coerce_checkbox("on") is True
    assert _coerce_checkbox("yes") is True
    assert _coerce_checkbox("1") is True


def test_coerce_checkbox_text_falsy():
    assert _coerce_checkbox("off") is False
    assert _coerce_checkbox("false") is False
    assert _coerce_checkbox("0") is False


def test_coerce_checkbox_empty_uses_default():
    assert _coerce_checkbox("", default=True) is True
    assert _coerce_checkbox("", default=False) is False


# ---------------------------------------------------------------------------
# _normalize_form_values
# ---------------------------------------------------------------------------


def test_normalize_form_values():
    aliases = {"x": ("a",), "y": ("b", "c")}
    defaults = {"x": "dx", "y": "dy"}
    out = _normalize_form_values({"a": 1, "c": 3}, aliases, defaults)
    assert out["x"] == 1
    assert out["y"] == 3


def test_normalize_form_values_uses_defaults():
    aliases = {"x": ("a",)}
    defaults = {"x": "dx"}
    out = _normalize_form_values({}, aliases, defaults)
    assert out["x"] == "dx"


def test_normalize_form_values_none_source():
    aliases = {"x": ("a",)}
    defaults = {"x": "dx"}
    out = _normalize_form_values(None, aliases, defaults)
    assert out["x"] == "dx"


# ---------------------------------------------------------------------------
# _extract_form_updates
# ---------------------------------------------------------------------------


def test_extract_form_updates_none():
    assert _extract_form_updates(None, {"x": ("a",)}) == {}


def test_extract_form_updates_present():
    out = _extract_form_updates({"a": 1}, {"x": ("a",)})
    assert out == {"x": 1}


def test_extract_form_updates_alternate_alias():
    out = _extract_form_updates({"b": 2}, {"x": ("a", "b")})
    assert out == {"x": 2}


def test_extract_form_updates_missing_key():
    out = _extract_form_updates({}, {"x": ("a",)})
    assert out == {}


# ---------------------------------------------------------------------------
# _merge_state
# ---------------------------------------------------------------------------


def test_merge_state_merges():
    base = {"a": 1, "b": 2}
    updates = {"b": 3, "c": 4}
    out = _merge_state(base, updates)
    assert out == {"a": 1, "b": 3, "c": 4}


def test_merge_state_empty_updates():
    base = {"a": 1}
    out = _merge_state(base, {})
    assert out == {"a": 1}


def test_merge_state_empty_base():
    out = _merge_state({}, {"a": 1})
    assert out == {"a": 1}


# ---------------------------------------------------------------------------
# _parse_int_input
# ---------------------------------------------------------------------------


def test_parse_int_input_valid():
    assert _parse_int_input("42", "x", 0) == 42


def test_parse_int_input_empty_uses_default():
    assert _parse_int_input("", "x", 99) == 99


def test_parse_int_input_invalid_raises():
    with pytest.raises(ValueError, match="整数"):
        _parse_int_input("not-int", "x", 0)


def test_parse_int_input_int_passes_through():
    assert _parse_int_input(7, "x", 0) == 7


# ---------------------------------------------------------------------------
# _parse_positive_int_input
# ---------------------------------------------------------------------------


def test_parse_positive_int_input():
    assert _parse_positive_int_input("42", "x", 1) == 42


def test_parse_positive_int_input_zero_clamped_to_one():
    """0 parses as 0, but max(1, 0) returns 1."""
    assert _parse_positive_int_input("0", "x", 1) == 1


def test_parse_positive_int_input_negative_clamped():
    assert _parse_positive_int_input("-5", "x", 1) == 1


def test_parse_positive_int_input_default():
    assert _parse_positive_int_input("", "x", 99) == 99


# ---------------------------------------------------------------------------
# _render_inline_error
# ---------------------------------------------------------------------------


def test_render_inline_error():
    out = _render_inline_error("Something broke")
    assert out is not None


# ---------------------------------------------------------------------------
# _set_download_error / _get_download_error
# ---------------------------------------------------------------------------


def test_set_download_error_then_get():
    iw_mod._download_error_message = None
    _set_download_error("boom")
    assert iw_mod._download_error_message == "boom"


def test_set_download_error_empty_clears():
    iw_mod._download_error_message = "old"
    _set_download_error("")
    assert iw_mod._download_error_message is None


def test_set_download_error_strips_whitespace():
    iw_mod._download_error_message = None
    _set_download_error("  boom  ")
    assert iw_mod._download_error_message == "boom"


def test_get_download_error_step5_uses_global():
    iw_mod._download_error_message = "global-msg"
    got = _get_download_error(step=5)
    assert got == "global-msg"


def test_get_download_error_step_not_5():
    iw_mod._download_error_message = "global-msg"
    got = _get_download_error(step=1)
    assert got is None


def test_get_download_error_explicit_overrides():
    got = _get_download_error(step=1, explicit_error="explicit")
    assert got == "explicit"


# ---------------------------------------------------------------------------
# _set_reconfigure_mode / _request_in_force_mode / _with_force_query
# ---------------------------------------------------------------------------


def test_set_reconfigure_mode():
    iw_mod._reconfigure_mode_active = False
    _set_reconfigure_mode(True)
    assert iw_mod._reconfigure_mode_active is True
    _set_reconfigure_mode(False)
    assert iw_mod._reconfigure_mode_active is False


def test_request_in_force_mode_true():
    req = MagicMock()
    req.query_params = {"force": "true"}
    assert _request_in_force_mode(req) is True


def test_request_in_force_mode_false():
    req = MagicMock()
    req.query_params = {"force": "false"}
    assert _request_in_force_mode(req) is False


def test_request_in_force_mode_no_force():
    req = MagicMock()
    req.query_params = {}
    assert _request_in_force_mode(req) is False


def test_with_force_query_not_in_reconfigure():
    iw_mod._reconfigure_mode_active = False
    out = _with_force_query("/path")
    assert out == "/path"


def test_with_force_query_in_reconfigure_no_q():
    iw_mod._reconfigure_mode_active = True
    out = _with_force_query("/path")
    assert "force=true" in out
    assert out == "/path?force=true"


def test_with_force_query_in_reconfigure_with_q():
    iw_mod._reconfigure_mode_active = True
    out = _with_force_query("/path?x=1")
    assert out == "/path?x=1&force=true"


# ---------------------------------------------------------------------------
# _update_sync_status
# ---------------------------------------------------------------------------


def test_update_sync_status_sets_progress():
    _update_sync_status(50, "mid", "half way", completed=False, error=None)
    assert iw_mod._sync_status["progress"] == 50
    assert iw_mod._sync_status["stage"] == "mid"
    assert iw_mod._sync_status["message"] == "half way"
    assert iw_mod._sync_status["completed"] is False
    assert iw_mod._sync_status["error"] is None


def test_update_sync_status_no_message_uses_stage():
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
    out = _runtime_form_state()
    assert isinstance(out, dict)
    assert "app_host" in out or "host" in out


def test_runtime_form_state_with_source():
    out = _runtime_form_state({"app_host": "0.0.0.0"})
    assert out["app_host"] == "0.0.0.0"


def test_runtime_form_state_localhost_only():
    out = _runtime_form_state({"app_host": "127.0.0.1"})
    # When host is 127.0.0.1, localhost_only should be True
    assert out.get("localhost_only") is True or out.get("app_localhost_only") is True


def test_gateway_form_state_default():
    out = _gateway_form_state()
    assert isinstance(out, dict)


def test_gateway_form_state_checkbox_enabled():
    out = _gateway_form_state({"gateway_enabled": "on"})
    assert out.get("gateway_enabled") is True


def test_gateway_form_state_checkbox_disabled():
    out = _gateway_form_state({"gateway_enabled": "off"})
    assert out.get("gateway_enabled") is False


def test_data_init_form_state_default():
    out = _data_init_form_state()
    assert isinstance(out, dict)


def test_data_init_form_state_with_source():
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
    """_wizard_step_meta returns dict for steps 1-6."""
    meta = _wizard_step_meta()
    assert len(meta) == 6
    for i in (1, 2, 3, 4, 5, 6):
        assert i in meta
        assert "title" in meta[i]
        assert "description" in meta[i]


def test_get_step_meta_returns_meta_for_known_steps():
    for s in (1, 2, 3, 4, 5, 6):
        meta = _get_step_meta(s)
        assert "title" in meta
        assert "description" in meta


def test_get_step_meta_unknown_falls_back_to_step1():
    meta = _get_step_meta(99)
    assert "title" in meta


# ---------------------------------------------------------------------------
# _check_password_strength
# ---------------------------------------------------------------------------


from quantide.web.pages.init_wizard import _check_password_strength


def test_password_too_short():
    strength, msg = _check_password_strength("aB1!")
    assert strength == "weak"
    assert "8" in msg or "长度" in msg


def test_password_strong():
    """All 4 categories + length >= 10 → strong."""
    strength, msg = _check_password_strength("Abcdef1!@#$%")
    assert strength == "strong"
    assert "强" in msg


def test_password_medium():
    """Exactly 3 of 4 categories, length 8-9 → medium."""
    strength, msg = _check_password_strength("Abcdefgh1")  # 9 chars: lower+upper+digit
    assert strength == "medium"


def test_password_weak_no_categories():
    """Only one category (just letters of one case)."""
    strength, msg = _check_password_strength("aaaaaaaa")
    assert strength == "weak"


def test_password_strong_no_special():
    """lower+upper+digit + length >= 10 → 3 categories, medium."""
    strength, msg = _check_password_strength("Abcdefghi1")
    assert strength == "medium"


def test_password_strong_with_8_chars_no_extra_categories():
    """8 chars, only one category → weak."""
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
    start, end = _calculate_download_range(1)
    today = __import__("datetime").date.today()
    assert end == today
    # ~365 days difference (allow +/-1 day for leap second)
    diff = (today - start).days
    assert 364 <= diff <= 366


def test_calculate_download_range_three_years():
    start, end = _calculate_download_range(3)
    today = __import__("datetime").date.today()
    assert end == today
    diff = (today - start).days
    assert 1094 <= diff <= 1097


def test_calculate_download_range_zero_years():
    start, end = _calculate_download_range(0)
    assert start == end


def test_render_download_range_info():
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
    """reset_initialization just calls init_wizard.reset_initialization."""
    import asyncio
    with patch.object(iw_mod, "init_wizard") as mock_iw:
        mock_iw.reset_initialization = AsyncMock()
        asyncio.run(reset_initialization())
    mock_iw.reset_initialization.assert_called_once()


def test_sync_progress_dialog():
    out = SyncProgressDialog()
    assert out is not None
