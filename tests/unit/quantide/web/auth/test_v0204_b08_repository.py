"""B08-auth-repository: Test UserRepository methods that don't need real db."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.auth.repository import UserRepository


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def repo(db):
    return UserRepository(db=db)


def test_count_by_role_empty(repo):
    """When no users, returns zeros."""
    repo.users = MagicMock()
    repo.users.return_value = []
    repo.list_all = MagicMock(return_value=[])
    got = repo.count_by_role()
    assert got == {"user": 0, "manager": 0, "admin": 0}


def test_count_by_role_mixed(repo):
    """Aggregates users by role."""
    u1 = MagicMock(role="user")
    u2 = MagicMock(role="user")
    u3 = MagicMock(role="admin")
    u4 = MagicMock(role="manager")
    u5 = MagicMock(role="unknown")  # not counted
    repo.list_all = MagicMock(return_value=[u1, u2, u3, u4, u5])
    got = repo.count_by_role()
    assert got["user"] == 2
    assert got["admin"] == 1
    assert got["manager"] == 1


def test_count_by_role_exception(repo):
    """When list_all raises, returns zeros."""
    repo.list_all = MagicMock(side_effect=Exception("boom"))
    got = repo.count_by_role()
    assert got == {"user": 0, "manager": 0, "admin": 0}


def test_search_users_no_filter(repo):
    users = [MagicMock(username="alice", email="a@x.com", role="user", active=True)]
    repo.list_all = MagicMock(return_value=users)
    got = repo.search_users(query="", role=None, active=None)
    assert got == users


def test_search_users_by_username_query(repo):
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="bob", email="b@x.com", role="user", active=True)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="ALI", role=None, active=None)
    assert u1 in got and u2 not in got


def test_search_users_by_email_query(repo):
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="bob", email="bob@x.com", role="user", active=True)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="bob@x", role=None, active=None)
    assert u2 in got


def test_search_users_by_role(repo):
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="admin", email="b@x.com", role="admin", active=True)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="", role="admin", active=None)
    assert u2 in got and u1 not in got


def test_search_users_by_active(repo):
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="bob", email="b@x.com", role="user", active=False)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="", role=None, active=False)
    assert u2 in got


def test_search_users_exception(repo):
    repo.list_all = MagicMock(side_effect=Exception("boom"))
    got = repo.search_users(query="x")
    assert got == []


def test_list_all_empty(repo):
    repo.users = MagicMock()
    repo.users.return_value = []
    got = repo.list_all()
    assert got == []


def test_list_all_with_users(repo):
    fake_dicts = [{"id": 1, "username": "a"}, {"id": 2, "username": "b"}]
    repo.users = MagicMock()
    repo.users.return_value = iter(fake_dicts)

    # Mock _dict_to_user
    with patch.object(repo, "_dict_to_user", side_effect=lambda d: f"user-{d['username']}"):
        got = repo.list_all()
    assert got == ["user-a", "user-b"]


def test_list_all_exception(repo):
    repo.users = MagicMock(side_effect=Exception("boom"))
    got = repo.list_all()
    assert got == []


def test_verify_password(repo):
    with patch("quantide.web.auth.repository.User.verify_password", return_value=True):
        assert repo.verify_password("pw", "hashed") is True
    with patch("quantide.web.auth.repository.User.verify_password", return_value=False):
        assert repo.verify_password("pw", "hashed") is False


def test_dict_to_user_returns_user(repo):
    user_dict = {
        "id": 1,
        "username": "alice",
        "email": "a@x.com",
        "password": "plaintext",
        "role": "user",
        "active": 1,
        "created_at": None,
        "last_login": None,
    }
    user = repo._dict_to_user(user_dict)
    assert user is not None


def test_dict_to_user_passthrough(repo):
    """If dict is already a User, returned as-is."""
    from quantide.web.auth.repository import User
    real_user = MagicMock(spec=User)
    real_user.username = "alice"
    got = repo._dict_to_user(real_user)
    assert got is real_user


from unittest.mock import patch
