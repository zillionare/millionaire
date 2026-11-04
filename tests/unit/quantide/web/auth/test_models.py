"""User model boundary behavior."""

from quantide.web.auth.models import User


def test_is_hashed_returns_a_boolean_for_empty_password() -> None:
    assert User.is_hashed("") is False
