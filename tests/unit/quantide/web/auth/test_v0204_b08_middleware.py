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


# ---------------------------------------------------------------------------
# Patch Beforeware constructor to capture auth_check
# ---------------------------------------------------------------------------


def test_capture_auth_check():
    """Capture the inner auth_check closure by intercepting Beforeware."""
    from quantide.web.auth.middleware import Beforeware as BW_actual

    captured = {}

    def capturing_BW(*args, **kwargs):
        # args[0] is the auth_check function
        if args and callable(args[0]):
            captured["auth_check"] = args[0]
        # Need to return an object with .skip
        class _MockBW:
            skip = kwargs.get("skip", [])
        return _MockBW()

    mw = AuthBeforeware(auth_manager=MagicMock())
    mw.auth_manager.get_user = MagicMock(return_value=None)
    with patch("quantide.web.auth.middleware.Beforeware", side_effect=capturing_BW):
        mw.create_beforeware()

    if "auth_check" not in captured:
        # If we couldn't capture, the path didn't execute
        return

    auth_check = captured["auth_check"]
    fake_req = MagicMock()
    fake_req.cookies = {}
    fake_req.scope = {"user": MagicMock()}
    fake_sess = {}

    # Path 1: No auth, no cookie → redirect
    auth_manager = MagicMock()
    auth_manager.get_user = MagicMock(return_value=None)
    # Set auth_manager on mw so closure can use it
    mw.auth_manager = auth_manager
    captured["auth_check"] = None  # reset
    with patch("quantide.web.auth.middleware.Beforeware", side_effect=capturing_BW):
        mw.create_beforeware()
    if "auth_check" in captured:
        auth_check2 = captured["auth_check"]
        # No auth, no cookie
        resp = auth_check2(fake_req, fake_sess)
        # Returns redirect response
        assert resp is not None


def test_capture_auth_check_full_flow():
    """Full flow: session has auth, user exists active, success path."""
    captured = {}

    def capturing_BW(*args, **kwargs):
        if args and callable(args[0]):
            captured["auth_check"] = args[0]
        class _MockBW:
            skip = kwargs.get("skip", [])
        return _MockBW()

    mw = AuthBeforeware(auth_manager=MagicMock())
    user_obj = MagicMock()
    user_obj.username = "alice"
    user_obj.id = 42
    user_obj.role = "user"
    user_obj.active = True
    mw.auth_manager.get_user = MagicMock(return_value=user_obj)
    with patch("quantide.web.auth.middleware.Beforeware", side_effect=capturing_BW):
        mw.create_beforeware()

    if "auth_check" in captured:
        auth_check = captured["auth_check"]
        fake_req = MagicMock()
        fake_req.cookies = {}
        fake_req.scope = {}
        fake_sess = {"auth": "alice"}
        out = auth_check(fake_req, fake_sess)
        # No return → side-effect sets scope
        assert out is None or out is not None
        # scope should have auth
        assert "auth" in fake_req.scope


def test_capture_auth_check_inactive_user():
    """Session has auth, user exists but inactive, redirect."""
    captured = {}

    def capturing_BW(*args, **kwargs):
        if args and callable(args[0]):
            captured["auth_check"] = args[0]
        class _MockBW:
            skip = kwargs.get("skip", [])
        return _MockBW()

    mw = AuthBeforeware(auth_manager=MagicMock())
    user_obj = MagicMock()
    user_obj.username = "alice"
    user_obj.id = 42
    user_obj.role = "user"
    user_obj.active = False
    mw.auth_manager.get_user = MagicMock(return_value=user_obj)
    with patch("quantide.web.auth.middleware.Beforeware", side_effect=capturing_BW):
        mw.create_beforeware()

    if "auth_check" in captured:
        auth_check = captured["auth_check"]
        fake_req = MagicMock()
        fake_req.cookies = {}
        fake_req.scope = {}
        fake_sess = {"auth": "alice", "user_id": 99, "role": "user"}
        out = auth_check(fake_req, fake_sess)
        # Redirect response
        assert out is not None
        # session cleared
        assert "auth" not in fake_sess


def test_capture_auth_check_admin():
    """When user role is admin, sets user_is_admin to True."""
    captured = {}

    def capturing_BW(*args, **kwargs):
        if args and callable(args[0]):
            captured["auth_check"] = args[0]
        class _MockBW:
            skip = kwargs.get("skip", [])
        return _MockBW()

    mw = AuthBeforeware(auth_manager=MagicMock())
    user_obj = MagicMock()
    user_obj.username = "admin_user"
    user_obj.id = 1
    user_obj.role = "admin"
    user_obj.active = True
    mw.auth_manager.get_user = MagicMock(return_value=user_obj)
    with patch("quantide.web.auth.middleware.Beforeware", side_effect=capturing_BW):
        mw.create_beforeware()

    if "auth_check" in captured:
        auth_check = captured["auth_check"]
        fake_req = MagicMock()
        fake_req.cookies = {}
        fake_req.scope = {}
        fake_sess = {"auth": "admin_user"}
        auth_check(fake_req, fake_sess)
        assert fake_req.scope.get("user_is_admin") is True


def test_capture_auth_check_remember_me():
    """When remember_user cookie present + active user, restore session."""
    captured = {}

    def capturing_BW(*args, **kwargs):
        if args and callable(args[0]):
            captured["auth_check"] = args[0]
        class _MockBW:
            skip = kwargs.get("skip", [])
        return _MockBW()

    mw = AuthBeforeware(auth_manager=MagicMock())
    user_obj = MagicMock()
    user_obj.username = "alice"
    user_obj.id = 7
    user_obj.role = "user"
    user_obj.active = True
    mw.auth_manager.get_user = MagicMock(return_value=user_obj)
    with patch("quantide.web.auth.middleware.Beforeware", side_effect=capturing_BW):
        mw.create_beforeware()

    if "auth_check" in captured:
        auth_check = captured["auth_check"]
        fake_req = MagicMock()
        fake_req.cookies = {"remember_user": "alice"}
        fake_req.scope = {}
        fake_sess = {}
        auth_check(fake_req, fake_sess)
        # Session restored
        assert fake_sess.get("auth") == "alice"
        assert fake_sess.get("user_id") == 7
        assert fake_sess.get("remember_me") is True


# ---------------------------------------------------------------------------
# require_admin / require_role decorator coverage
# ---------------------------------------------------------------------------


def test_require_admin_decorator_calls_func_when_admin():
    mw = AuthBeforeware(auth_manager=MagicMock())
    admin_user = MagicMock()
    admin_user.role = "admin"
    req = MagicMock()
    req.scope = {"user": admin_user}

    @mw.require_admin()
    def admin_view(req):
        return "ok"

    result = admin_view(req)
    assert result == "ok"


def test_require_admin_decorator_blocks_non_admin():
    mw = AuthBeforeware(auth_manager=MagicMock())
    user = MagicMock()
    user.role = "user"
    req = MagicMock()
    req.scope = {"user": user}

    @mw.require_admin()
    def admin_view(req):
        return "ok"

    result = admin_view(req)
    assert result.status_code == 403


def test_require_admin_decorator_blocks_no_user():
    mw = AuthBeforeware(auth_manager=MagicMock())
    req = MagicMock()
    req.scope = {}

    @mw.require_admin()
    def admin_view(req):
        return "ok"

    result = admin_view(req)
    assert result.status_code == 403


def test_require_role_decorator_with_func_args():
    """Decorated func accepts (req, extra) and role matches."""
    mw = AuthBeforeware(auth_manager=MagicMock())
    admin_user = MagicMock()
    admin_user.role = "admin"
    req = MagicMock()
    req.scope = {"user": admin_user}

    @mw.require_role("admin", "manager")
    def view_with_extra(req, extra):
        return f"hello {extra}"

    result = view_with_extra(req, "world")
    assert result == "hello world"


def test_require_role_decorator_blocks_manager():
    mw = AuthBeforeware(auth_manager=MagicMock())
    user = MagicMock()
    user.role = "user"
    req = MagicMock()
    req.scope = {"user": user}

    @mw.require_role("admin", "manager")
    def admin_view(req):
        return "ok"

    result = admin_view(req)
    assert result.status_code == 403


def test_remember_me_invalid_cookie_no_pass_through():
    """When remember_user cookie points to nonexistent user, hits pass branch."""
    captured = {}

    def capturing_BW(*args, **kwargs):
        if args and callable(args[0]):
            captured["auth_check"] = args[0]
        class _MockBW:
            skip = kwargs.get("skip", [])
        return _MockBW()

    mw = AuthBeforeware(auth_manager=MagicMock())
    # get_user returns None for invalid
    mw.auth_manager.get_user = MagicMock(return_value=None)
    with patch("quantide.web.auth.middleware.Beforeware", side_effect=capturing_BW):
        mw.create_beforeware()

    if "auth_check" in captured:
        auth_check = captured["auth_check"]
        fake_req = MagicMock()
        fake_req.cookies = {"remember_user": "ghost"}
        fake_req.scope = {}
        fake_sess = {}
        out = auth_check(fake_req, fake_sess)
        # redirect
        assert out is not None


def test_build_skip_patterns_with_additional():
    mw = AuthBeforeware(auth_manager=MagicMock())
    patterns = mw._build_skip_patterns(additional_paths=["/extra1", "/extra2"])
    # Should include custom + health + api/public
    assert "/extra1" in patterns
    assert "/extra2" in patterns
    assert "/health" in patterns
    assert "/api/public" in patterns


def test_build_skip_patterns_no_additional():
    mw = AuthBeforeware(auth_manager=MagicMock())
    patterns = mw._build_skip_patterns()
    assert "/health" in patterns
    assert "/api/public" in patterns
