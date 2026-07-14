"""B08-auth-forms: Test small helpers in web/auth/forms.py."""

from __future__ import annotations

from quantide.web.auth import forms as forms_mod
from quantide.web.auth.forms import (
    InfoRow,
    _brand_emblem,
    _login_error_message,
    _login_field,
    create_message_alert,
)


# ---------------------------------------------------------------------------
# _login_error_message
# ---------------------------------------------------------------------------


def test_login_error_message_missing_fields_returns_none():
    """missing_fields has no specific mapping, returns None."""
    msg = _login_error_message("missing_fields")
    assert msg is None


def test_login_error_message_invalid():
    """Invalid mapping is for the 'invalid' key."""
    msg = _login_error_message("invalid")
    assert "账号或密码" in msg


def test_login_error_message_inactive():
    msg = _login_error_message("inactive")
    assert "停用" in msg


def test_login_error_message_system():
    msg = _login_error_message("system")
    assert "系统" in msg


def test_login_error_message_unknown_returns_none():
    """Unknown error key returns None (caller falls back)."""
    msg = _login_error_message("unknown_error")
    assert msg is None


def test_login_error_message_none_returns_none():
    msg = _login_error_message(None)
    assert msg is None


# ---------------------------------------------------------------------------
# _login_field
# ---------------------------------------------------------------------------


def test_login_field_basic():
    out = _login_field(
        label_cn="用户名",
        label_en="Username",
        field_id="u",
        name="username",
        placeholder="",
    )
    assert out is not None


def test_login_field_password_type():
    out = _login_field(
        label_cn="密码",
        label_en="Password",
        field_id="p",
        name="password",
        placeholder="",
        field_type="password",
    )
    assert out is not None


def test_login_field_with_placeholder():
    out = _login_field(
        label_cn="U",
        label_en="U",
        field_id="u",
        name="username",
        placeholder="Enter username",
    )
    assert out is not None


# ---------------------------------------------------------------------------
# _brand_emblem
# ---------------------------------------------------------------------------


def test_brand_emblem():
    out = _brand_emblem()
    assert out is not None


# ---------------------------------------------------------------------------
# create_message_alert
# ---------------------------------------------------------------------------


def test_create_message_alert_info():
    out = create_message_alert("hello", "info")
    assert out is not None


def test_create_message_alert_error():
    out = create_message_alert("bad", "error")
    assert out is not None


def test_create_message_alert_success():
    out = create_message_alert("ok", "success")
    assert out is not None


def test_create_message_alert_warning():
    out = create_message_alert("warn", "warning")
    assert out is not None


def test_create_message_alert_default_type():
    out = create_message_alert("default")
    assert out is not None


def test_create_message_alert_unknown_type():
    out = create_message_alert("unknown", "weird-type")
    assert out is not None


# ---------------------------------------------------------------------------
# InfoRow
# ---------------------------------------------------------------------------


def test_info_row():
    out = InfoRow("Label", "Value")
    assert out is not None


def test_info_row_with_int():
    out = InfoRow("Count", 42)
    assert out is not None


# ---------------------------------------------------------------------------
# create_register_form error message variants
# ---------------------------------------------------------------------------


from quantide.web.auth.forms import (
    create_forgot_password_form,
    create_register_form,
    create_reset_password_form,
)


def test_register_form_username_taken():
    out = create_register_form(error="username_taken")
    assert out is not None


def test_register_form_email_taken():
    out = create_register_form(error="email_taken")
    assert out is not None


def test_register_form_password_mismatch():
    out = create_register_form(error="password_mismatch")
    assert out is not None


def test_register_form_password_weak():
    out = create_register_form(error="password_weak")
    assert out is not None


def test_register_form_invalid_email():
    out = create_register_form(error="invalid_email")
    assert out is not None


def test_register_form_creation_failed():
    out = create_register_form(error="creation_failed")
    assert out is not None


def test_register_form_terms_required():
    out = create_register_form(error="terms_required")
    assert out is not None


def test_register_form_unknown_error():
    out = create_register_form(error="unknown")
    assert out is not None


def test_forgot_form_email_not_found():
    out = create_forgot_password_form(error="email_not_found")
    assert out is not None


def test_forgot_form_send_failed():
    out = create_forgot_password_form(error="send_failed")
    assert out is not None


def test_forgot_form_success():
    out = create_forgot_password_form(success="sent")
    assert out is not None


def test_reset_form_invalid_token():
    out = create_reset_password_form(token="abc", error="invalid_token")
    assert out is not None


def test_reset_form_password_mismatch():
    out = create_reset_password_form(token="abc", error="password_mismatch")
    assert out is not None


def test_reset_form_password_weak():
    out = create_reset_password_form(token="abc", error="password_weak")
    assert out is not None


def test_reset_form_unknown_error():
    out = create_reset_password_form(token="abc", error="unknown")
    assert out is not None
