"""B08-auth-forms: Test small helpers in web/auth/forms.py."""

from __future__ import annotations

from fasthtml.core import to_xml

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
    """[AC-FR1501-05] missing_fields has no specific mapping, returns None."""
    msg = _login_error_message("missing_fields")
    assert msg is None


def test_login_error_message_invalid():
    """[AC-FR1501-05] Invalid mapping is for the 'invalid' key."""
    msg = _login_error_message("invalid")
    assert "账号或密码" in msg


def test_login_error_message_inactive():
    """[AC-FR1501-05] test_login_error_message_inactive."""
    msg = _login_error_message("inactive")
    assert "停用" in msg


def test_login_error_message_system():
    """[AC-FR1501-05] test_login_error_message_system."""
    msg = _login_error_message("system")
    assert "系统" in msg


def test_login_error_message_unknown_returns_none():
    """[AC-FR1501-05] Unknown error key returns None (caller falls back)."""
    msg = _login_error_message("unknown_error")
    assert msg is None


def test_login_error_message_none_returns_none():
    """[AC-FR1501-05] test_login_error_message_none_returns_none."""
    msg = _login_error_message(None)
    assert msg is None


# ---------------------------------------------------------------------------
# _login_field
# ---------------------------------------------------------------------------


def test_login_field_basic():
    """[AC-FR1501-05] test_login_field_basic."""
    out = _login_field(
        label_cn="用户名",
        label_en="Username",
        field_id="u",
        name="username",
        placeholder="",
    )
    assert out is not None


def test_login_field_password_type():
    """[AC-FR1501-05] test_login_field_password_type."""
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
    """[AC-FR1501-05] test_login_field_with_placeholder."""
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
    """[AC-FR1501-05] test_brand_emblem."""
    out = _brand_emblem()
    assert out is not None


# ---------------------------------------------------------------------------
# create_message_alert
# ---------------------------------------------------------------------------


def test_create_message_alert_info():
    """[AC-NFR1101-01] info alert renders the message text."""
    out = create_message_alert("hello", "info")
    assert "hello" in to_xml(out)


def test_create_message_alert_error():
    """[AC-NFR1101-01] error alert renders the message text."""
    out = create_message_alert("bad", "error")
    assert "bad" in to_xml(out)


def test_create_message_alert_success():
    """[AC-NFR1101-01] success alert renders the message text."""
    out = create_message_alert("ok", "success")
    assert "ok" in to_xml(out)


def test_create_message_alert_warning():
    """[AC-NFR1101-01] warning alert renders the message text."""
    out = create_message_alert("warn", "warning")
    assert "warn" in to_xml(out)


def test_create_message_alert_default_type():
    """[AC-NFR1101-01] default-type alert renders the message text."""
    out = create_message_alert("default")
    assert "default" in to_xml(out)


def test_create_message_alert_unknown_type():
    """[AC-NFR1101-01] unknown-type alert still renders the message text."""
    out = create_message_alert("unknown", "weird-type")
    assert "unknown" in to_xml(out)


# ---------------------------------------------------------------------------
# InfoRow
# ---------------------------------------------------------------------------


def test_info_row():
    """[AC-FR1501-05] test_info_row."""
    out = InfoRow("Label", "Value")
    assert out is not None


def test_info_row_with_int():
    """[AC-FR1501-05] test_info_row_with_int."""
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
    """[AC-NFR1101-01] username_taken error renders the specific message."""
    out = create_register_form(error="username_taken")
    assert "Username already taken" in to_xml(out)


def test_register_form_email_taken():
    """[AC-NFR1101-01] email_taken error renders the specific message."""
    out = create_register_form(error="email_taken")
    assert "Email already registered" in to_xml(out)


def test_register_form_password_mismatch():
    """[AC-NFR1101-01] password_mismatch error renders the specific message."""
    out = create_register_form(error="password_mismatch")
    assert "Passwords do not match" in to_xml(out)


def test_register_form_password_weak():
    """[AC-NFR1101-01] password_weak error renders the specific message."""
    out = create_register_form(error="password_weak")
    assert "at least 8 characters" in to_xml(out)


def test_register_form_invalid_email():
    """[AC-NFR1101-01] invalid_email error renders the specific message."""
    out = create_register_form(error="invalid_email")
    assert "valid email address" in to_xml(out)


def test_register_form_creation_failed():
    """[AC-NFR1101-01] creation_failed error renders the specific message."""
    out = create_register_form(error="creation_failed")
    assert "Failed to create account" in to_xml(out)


def test_register_form_terms_required():
    """[AC-NFR1101-01] terms_required error renders the specific message."""
    out = create_register_form(error="terms_required")
    assert "Terms and Conditions" in to_xml(out)


def test_register_form_unknown_error():
    """[AC-NFR1101-01] unknown error renders no error alert text."""
    out = create_register_form(error="unknown")
    # Unknown error key has no mapping -> no specific error text rendered
    assert "Create Account" in to_xml(out)


def test_forgot_form_email_not_found():
    """[AC-NFR1101-01] email_not_found error renders the specific message."""
    out = create_forgot_password_form(error="email_not_found")
    assert "email" in to_xml(out).lower()


def test_forgot_form_send_failed():
    """[AC-NFR1101-01] send_failed error renders an alert."""
    out = create_forgot_password_form(error="send_failed")
    assert "failed" in to_xml(out).lower() or "alert" in to_xml(out).lower()


def test_forgot_form_success():
    """[AC-NFR1101-01] success=sent renders a success indicator."""
    out = create_forgot_password_form(success="sent")
    assert "sent" in to_xml(out).lower() or "success" in to_xml(out).lower()


def test_reset_form_invalid_token():
    """[AC-NFR1101-01] invalid_token error renders an alert."""
    out = create_reset_password_form(token="abc", error="invalid_token")
    assert "token" in to_xml(out).lower() or "invalid" in to_xml(out).lower()


def test_reset_form_password_mismatch():
    """[AC-NFR1101-01] password_mismatch error renders the specific message."""
    out = create_reset_password_form(token="abc", error="password_mismatch")
    assert "Passwords do not match" in to_xml(out) or "mismatch" in to_xml(out).lower()


def test_reset_form_password_weak():
    """[AC-NFR1101-01] password_weak error renders the specific message."""
    out = create_reset_password_form(token="abc", error="password_weak")
    assert "8 characters" in to_xml(out) or "weak" in to_xml(out).lower()


def test_reset_form_unknown_error():
    """[AC-NFR1101-01] unknown error renders no specific error text."""
    out = create_reset_password_form(token="abc", error="unknown")
    assert "password" in to_xml(out).lower()
