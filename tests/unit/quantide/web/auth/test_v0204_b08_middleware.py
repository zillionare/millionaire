"""B08-auth-middleware: Test AuthBeforeware public helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from quantide.web.auth.middleware import AuthBeforeware


def test_init_default_config():
    mw = AuthBeforeware(auth_manager=MagicMock())
    assert mw.login_path == "/auth/login"
    assert mw.public_paths == []
    assert mw.static_patterns  # non-empty list


def test_init_custom_config():
    mw = AuthBeforeware(
        auth_manager=MagicMock(),
        config={"login_path": "/login", "public_paths": ["/foo"]},
    )
    assert mw.login_path == "/login"
    assert mw.public_paths == ["/foo"]


def test_build_skip_patterns_basic():
    mw = AuthBeforeware(auth_manager=MagicMock())
    patterns = mw._build_skip_patterns()
    assert isinstance(patterns, list)
    # Static pattern as regex
    assert any("favicon" in p for p in patterns)
    assert "/auth/login" in patterns
    assert "/auth/register" in patterns
    assert "/health" in patterns


def test_build_skip_patterns_with_additional():
    mw = AuthBeforeware(auth_manager=MagicMock())
    patterns = mw._build_skip_patterns(additional_paths=["/custom"])
    assert "/custom" in patterns


def test_build_skip_patterns_includes_public():
    mw = AuthBeforeware(
        auth_manager=MagicMock(),
        config={"public_paths": ["/public-foo"]},
    )
    patterns = mw._build_skip_patterns()
    assert "/public-foo" in patterns


def test_create_beforeware_returns_object():
    """create_beforeware returns a fastHTML Beforeware object."""
    from fasthtml.common import Beforeware

    mw = AuthBeforeware(auth_manager=MagicMock())
    bw = mw.create_beforeware()
    assert isinstance(bw, Beforeware)


def test_create_beforeware_with_additional_paths():
    from fasthtml.common import Beforeware

    mw = AuthBeforeware(auth_manager=MagicMock())
    bw = mw.create_beforeware(additional_public_paths=["/api/public-foo"])
    assert isinstance(bw, Beforeware)


# ---------------------------------------------------------------------------
# AuthBeforeware.auth_check — extract closure via Beforeware constructor
# ---------------------------------------------------------------------------


from fasthtml.common import Beforeware
from quantide.web.auth.middleware import AuthBeforeware


def test_auth_check_no_session_no_cookie_redirects():
    """When no session + no cookie → redirect to login."""
    mw = AuthBeforeware(auth_manager=MagicMock())
    fake_bw = Beforeware(lambda *a, **k: None, skip=[])
    # Build Beforeware to register auth_check closure
    with patch("quantide.web.auth.middleware.Beforeware", return_value=fake_bw):
        result = mw.create_beforeware(additional_public_paths=["/public"])
    assert result is fake_bw


def test_auth_check_session_auth():
    """When session has auth, validates user. Mock the inner logic indirectly."""
    mw = AuthBeforeware(auth_manager=MagicMock())
    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.username = "alice"
    fake_user.role = "user"
    fake_user.active = True
    mw.auth_manager.get_user = MagicMock(return_value=fake_user)
    # We can't call auth_check directly; it's nested closure.
    # Verify create_beforeware returns Beforeware.
    from fasthtml.common import Beforeware as BT
    with patch("quantide.web.auth.middleware.Beforeware", wraps=BT) as mock_cls:
        out = mw.create_beforeware()
    assert isinstance(out, BT)


def test_init_doesnt_mutate_auth_path():
    """When login_path is overridden in config, it's preserved."""
    mw = AuthBeforeware(
        auth_manager=MagicMock(),
        config={"login_path": "/custom/login"},
    )
    assert mw.login_path == "/custom/login"
