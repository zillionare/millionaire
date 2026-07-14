"""B08-init-wizard-helpers: Test small helper functions in init_wizard.py."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from quantide.web.pages import init_wizard as iw_mod
from quantide.web.pages.init_wizard import (
    _coerce_checkbox,
    _extract_form_updates,
    _format_date_zh,
    _merge_state,
    _normalize_form_values,
    _parse_epoch_input,
    _parse_int_input,
    _parse_positive_int_input,
    _pick_first_value,
    _render_inline_error,
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
