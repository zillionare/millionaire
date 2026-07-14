"""B08-web-1: Tests for quantide/web/auth/utils.py.

Target: raise coverage from 0% to >=95% (v0.2-added file).
"""

from __future__ import annotations

import re
import string

import pytest

from quantide.web.auth.utils import (
    generate_token,
    sanitize_username,
    validate_email,
    validate_password,
)


# ---------------------------------------------------------------------------
# generate_token
# ---------------------------------------------------------------------------


def test_generate_token_default_length():
    tok = generate_token()
    assert len(tok) == 32


def test_generate_token_custom_length():
    tok = generate_token(64)
    assert len(tok) == 64


def test_generate_token_uses_safe_alphabet():
    """Token characters are restricted to ASCII letters + digits."""
    tok = generate_token(128)
    allowed = set(string.ascii_letters + string.digits)
    for ch in tok:
        assert ch in allowed


def test_generate_token_returns_string():
    tok = generate_token()
    assert isinstance(tok, str)


def test_generate_token_unique_per_call():
    a = generate_token(40)
    b = generate_token(40)
    assert a != b


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------


def test_validate_email_accepts_valid():
    assert validate_email("user@example.com") is True
    assert validate_email("a.b+tag@sub.example.co") is True


def test_validate_email_rejects_empty():
    assert validate_email("") is False


def test_validate_email_rejects_no_at_sign():
    assert validate_email("userexample.com") is False


def test_validate_email_rejects_missing_tld():
    assert validate_email("user@example") is False


def test_validate_email_rejects_invalid_chars():
    assert validate_email("us!er@example.com") is False


def test_validate_email_rejects_missing_domain():
    assert validate_email("user@") is False


def test_validate_email_rejects_too_short_tld():
    assert validate_email("user@example.c") is False


# ---------------------------------------------------------------------------
# validate_password
# ---------------------------------------------------------------------------


def test_validate_password_empty_returns_error():
    valid, msg = validate_password("")
    assert valid is False
    assert msg == "Password is required"


def test_validate_password_too_short():
    valid, msg = validate_password("Abc1!@#")
    assert valid is False
    assert "8 characters" in msg


def test_validate_password_missing_digit():
    valid, msg = validate_password("Abcdefgh")
    assert valid is False
    assert "number" in msg.lower()


def test_validate_password_missing_uppercase():
    valid, msg = validate_password("abcdefg1")
    assert valid is False
    assert "uppercase" in msg.lower()


def test_validate_password_valid_returns_true():
    valid, msg = validate_password("Abcdefg1")
    assert valid is True
    assert msg == ""


def test_validate_password_with_special_chars_and_long():
    valid, msg = validate_password("MyStr0ng!Passw0rd2024")
    assert valid is True


# ---------------------------------------------------------------------------
# sanitize_username
# ---------------------------------------------------------------------------


def test_sanitize_username_keeps_alphanumeric():
    assert sanitize_username("user_123") == "user_123"


def test_sanitize_username_lowercases_result():
    assert sanitize_username("USER") == "user"


def test_sanitize_username_removes_special_chars():
    assert sanitize_username("us!er@name") == "username"


def test_sanitize_username_strips_spaces():
    assert sanitize_username("user name") == "username"


def test_sanitize_username_empty_returns_empty():
    assert sanitize_username("") == ""


def test_sanitize_username_keeps_underscores():
    assert sanitize_username("test_user_001") == "test_user_001"


def test_sanitize_username_strips_dots():
    assert sanitize_username("foo.bar") == "foobar"
