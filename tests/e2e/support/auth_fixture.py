"""Explicit test-administrator fixtures.

Production no longer creates a default administrator.  Authenticated tests must
seed their own administrator after the app's auth database is initialized.
"""

from __future__ import annotations

from quantide.web.auth.manager import AuthManager

TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "admin123"
TEST_ADMIN_EMAIL = "admin@system.local"


def ensure_test_admin(
    auth: AuthManager | None = None,
    *,
    username: str = TEST_ADMIN_USERNAME,
    password: str = TEST_ADMIN_PASSWORD,
    email: str = TEST_ADMIN_EMAIL,
    role: str = "admin",
):
    """Create or repair the explicit test administrator on the active auth DB.

    Call this only after ``create_app`` (or ``AuthManager.initialize``) so the
    singleton points at the isolated test database.
    """
    manager = auth or AuthManager.get_instance()
    if manager is None:
        manager = AuthManager()
    if manager.user_repo is None:
        manager.initialize()

    repo = manager.user_repo
    if repo is None:
        raise RuntimeError("auth repository is not initialized")

    existing = repo.get_by_username(username)
    if existing is None:
        return repo.create(
            username=username,
            email=email,
            password=password,
            role=role,
        )

    if existing.id is None:
        raise RuntimeError("test admin account is missing its primary key")
    if not repo.verify_password(password, existing.password):
        if not repo.update(existing.id, password=password):
            raise RuntimeError("failed to update explicit test admin password")
    return repo.get_by_username(username)


def sign_in_test_admin(client):
    """Authenticate page-unit clients using their isolated administrator."""
    from unittest.mock import patch

    from quantide.service.init_wizard import init_wizard

    ensure_test_admin()
    with patch.object(init_wizard, "is_initialized", return_value=True):
        response = client.post('/auth/login', data={'username': TEST_ADMIN_USERNAME,
                                                   'password': TEST_ADMIN_PASSWORD},
                               follow_redirects=False)
    assert response.status_code == 303
