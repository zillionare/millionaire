"""B08-auth-middleware: Test AuthBeforeware public helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

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
