"""B09-init-wizard-helpers2: Edge-case tests for init_wizard helper functions."""

from __future__ import annotations

import pytest

from quantide.web.pages.init_wizard import (
    DATA_INIT_FIELD_ALIASES,
    DATA_INIT_FORM_FIELDS,
    GATEWAY_FIELD_ALIASES,
    GATEWAY_FORM_FIELDS,
    GATEWAY_DEFAULTS,
    RUNTIME_DEFAULTS,
    RUNTIME_FIELD_ALIASES,
    RUNTIME_FORM_FIELDS,
    _coerce_checkbox,
    _data_init_form_state,
    _extract_form_updates,
    _gateway_form_state,
    _merge_state,
    _normalize_form_values,
    _parse_int_input,
    _parse_positive_int_input,
    _runtime_form_state,
)


# ---------------------------------------------------------------------------
# _parse_int_input edge cases
# ---------------------------------------------------------------------------


def test_parse_int_input_strips_whitespace():
    """[AC-NFR1101-01] Whitespace-padded numeric string parses correctly."""
    assert _parse_int_input("  42  ", "x", 0) == 42


def test_parse_int_input_float_like_string_raises():
    """[AC-NFR1101-01] Float-like string raises ValueError with label."""
    with pytest.raises(ValueError, match="端口"):
        _parse_int_input("3.14", "端口", 0)


def test_parse_int_input_none_value_uses_default():
    """[AC-NFR1101-01] None value falls back to default (str(None).strip() = 'None' -> raises, but default branch empty)."""
    # str(None).strip() == "None" which is not empty -> int("None") raises
    with pytest.raises(ValueError, match="整数"):
        _parse_int_input(None, "整数标签", 0)


# ---------------------------------------------------------------------------
# _parse_positive_int_input edge cases
# ---------------------------------------------------------------------------


def test_parse_positive_int_input_large_value():
    """[AC-NFR1101-01] Large positive value passes through unchanged."""
    assert _parse_positive_int_input("999999", "x", 1) == 999999


def test_parse_positive_int_input_empty_string_uses_default():
    """[AC-NFR1101-01] Empty string returns default (default not clamped if > 0)."""
    assert _parse_positive_int_input("", "x", 5) == 5


# ---------------------------------------------------------------------------
# _normalize_form_values edge cases
# ---------------------------------------------------------------------------


def test_normalize_form_values_picks_first_alias_only():
    """[AC-NFR1101-01] When multiple aliases present, first matching key wins."""
    aliases = {"x": ("a", "b")}
    defaults = {"x": "dx"}
    # Both keys present; "a" should win
    out = _normalize_form_values({"a": 1, "b": 2}, aliases, defaults)
    assert out["x"] == 1


def test_normalize_form_values_preserves_none_value():
    """[AC-NFR1101-01] Explicitly None value is returned as-is (not default)."""
    aliases = {"x": ("a",)}
    defaults = {"x": "dx"}
    out = _normalize_form_values({"a": None}, aliases, defaults)
    assert out["x"] is None


# ---------------------------------------------------------------------------
# _extract_form_updates edge cases
# ---------------------------------------------------------------------------


def test_extract_form_updates_multiple_fields():
    """[AC-NFR1101-01] Multiple fields extracted with first-match alias."""
    aliases = {"x": ("a", "b"), "y": ("c",)}
    out = _extract_form_updates({"a": 1, "c": 3}, aliases)
    assert out == {"x": 1, "y": 3}


def test_extract_form_updates_first_alias_wins():
    """[AC-NFR1101-01] First alias present -> second alias ignored."""
    aliases = {"x": ("a", "b")}
    out = _extract_form_updates({"a": 1, "b": 2}, aliases)
    assert out == {"x": 1}


# ---------------------------------------------------------------------------
# _merge_state edge cases
# ---------------------------------------------------------------------------


def test_merge_state_updates_override_base():
    """[AC-NFR1101-01] Updates override base values for same key."""
    base = {"a": 1, "b": 2, "c": 3}
    updates = {"b": 99, "d": 4}
    out = _merge_state(base, updates)
    assert out == {"a": 1, "b": 99, "c": 3, "d": 4}


def test_merge_state_does_not_mutate_base():
    """[AC-NFR1101-01] Base dict is not mutated by merge."""
    base = {"a": 1}
    _merge_state(base, {"b": 2})
    assert base == {"a": 1}


# ---------------------------------------------------------------------------
# _runtime_form_state edge cases
# ---------------------------------------------------------------------------


def test_runtime_form_state_empty_host_falls_back_to_default():
    """[AC-NFR1101-01] Empty host string falls back to default host."""
    out = _runtime_form_state({RUNTIME_FORM_FIELDS["host"]: ""})
    assert out[RUNTIME_FORM_FIELDS["host"]] == RUNTIME_DEFAULTS[RUNTIME_FORM_FIELDS["host"]]


def test_runtime_form_state_localhost_only_false_for_external_host():
    """[AC-NFR1101-01] Non-localhost host sets localhost_only to False."""
    out = _runtime_form_state({RUNTIME_FORM_FIELDS["host"]: "0.0.0.0"})
    assert out[RUNTIME_FORM_FIELDS["localhost_only"]] is False


def test_runtime_form_state_localhost_only_true_for_127():
    """[AC-NFR1101-01] 127.0.0.1 host sets localhost_only to True."""
    out = _runtime_form_state({RUNTIME_FORM_FIELDS["host"]: "127.0.0.1"})
    assert out[RUNTIME_FORM_FIELDS["localhost_only"]] is True


# ---------------------------------------------------------------------------
# _gateway_form_state edge cases
# ---------------------------------------------------------------------------


def test_gateway_form_state_enabled_default_true():
    """[AC-NFR1101-01] Default gateway_enabled is True."""
    out = _gateway_form_state()
    assert out[GATEWAY_FORM_FIELDS["enabled"]] is True


def test_gateway_form_state_enabled_explicit_bool():
    """[AC-NFR1101-01] Explicit bool value preserved."""
    out = _gateway_form_state({GATEWAY_FORM_FIELDS["enabled"]: False})
    assert out[GATEWAY_FORM_FIELDS["enabled"]] is False


def test_gateway_form_state_enabled_string_true():
    """[AC-NFR1101-01] String 'true' coerced to True."""
    out = _gateway_form_state({GATEWAY_FORM_FIELDS["enabled"]: "true"})
    assert out[GATEWAY_FORM_FIELDS["enabled"]] is True


def test_gateway_form_state_prefix_from_state_prefix_alias():
    """[AC-NFR1101-01] state_prefix alias populates prefix field."""
    out = _gateway_form_state({GATEWAY_FORM_FIELDS["state_prefix"]: "/custom"})
    assert out[GATEWAY_FORM_FIELDS["prefix"]] == "/custom"


# ---------------------------------------------------------------------------
# _data_init_form_state edge cases
# ---------------------------------------------------------------------------


def test_data_init_form_state_all_fields_from_source():
    """[AC-NFR1101-01] All data-init fields populated from source."""
    src = {
        DATA_INIT_FORM_FIELDS["epoch"]: "2020-01-01",
        DATA_INIT_FORM_FIELDS["data_source"]: "akshare",
        DATA_INIT_FORM_FIELDS["tushare_token"]: "tok123",
        DATA_INIT_FORM_FIELDS["history_years"]: "3",
    }
    out = _data_init_form_state(src)
    assert out[DATA_INIT_FORM_FIELDS["epoch"]] == "2020-01-01"
    assert out[DATA_INIT_FORM_FIELDS["data_source"]] == "akshare"
    assert out[DATA_INIT_FORM_FIELDS["tushare_token"]] == "tok123"
    assert out[DATA_INIT_FORM_FIELDS["history_years"]] == "3"


def test_data_init_form_state_none_source_uses_defaults():
    """[AC-NFR1101-01] None source returns all defaults."""
    out = _data_init_form_state(None)
    assert out[DATA_INIT_FORM_FIELDS["data_source"]] == "tushare"


# ---------------------------------------------------------------------------
# _coerce_checkbox edge cases
# ---------------------------------------------------------------------------


def test_coerce_checkbox_case_insensitive_falsy():
    """[AC-NFR1101-01] Uppercase falsy strings coerced to False."""
    assert _coerce_checkbox("FALSE") is False
    assert _coerce_checkbox("Off") is False
    assert _coerce_checkbox("NO") is False


def test_coerce_checkbox_case_insensitive_truthy():
    """[AC-NFR1101-01] Mixed-case truthy strings coerced to True."""
    assert _coerce_checkbox("ON") is True
    assert _coerce_checkbox("Yes") is True
    assert _coerce_checkbox("TRUE") is True


def test_coerce_checkbox_unknown_string_is_truthy():
    """[AC-NFR1101-01] Unknown non-falsy string treated as True."""
    assert _coerce_checkbox("maybe") is True
    assert _coerce_checkbox("1") is True


def test_coerce_checkbox_int_value_coerced_via_str():
    """[AC-NFR1101-01] Integer 0 coerced to False, non-zero to True."""
    assert _coerce_checkbox(0) is False
    assert _coerce_checkbox(1) is True


# ---------------------------------------------------------------------------
# Combined helper flow
# ---------------------------------------------------------------------------


def test_runtime_then_merge_state_flow():
    """[AC-NFR1101-01] Runtime form state merged with updates preserves structure."""
    base = _runtime_form_state()
    updates = _extract_form_updates(
        {RUNTIME_FORM_FIELDS["port"]: "9000"},
        RUNTIME_FIELD_ALIASES,
    )
    merged = _merge_state(base, updates)
    assert merged[RUNTIME_FORM_FIELDS["port"]] == "9000"
    assert RUNTIME_FORM_FIELDS["host"] in merged
