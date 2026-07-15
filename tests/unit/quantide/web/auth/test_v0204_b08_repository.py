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
    """[AC-FR1501-06] When no users, returns zeros."""
    repo.users = MagicMock()
    repo.users.return_value = []
    repo.list_all = MagicMock(return_value=[])
    got = repo.count_by_role()
    assert got == {"user": 0, "manager": 0, "admin": 0}


def test_count_by_role_mixed(repo):
    """[AC-FR1501-06] Aggregates users by role."""
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
    """[AC-FR1501-06] When list_all raises, returns zeros."""
    repo.list_all = MagicMock(side_effect=Exception("boom"))
    got = repo.count_by_role()
    assert got == {"user": 0, "manager": 0, "admin": 0}


def test_search_users_no_filter(repo):
    """[AC-FR1501-06] test_search_users_no_filter."""
    users = [MagicMock(username="alice", email="a@x.com", role="user", active=True)]
    repo.list_all = MagicMock(return_value=users)
    got = repo.search_users(query="", role=None, active=None)
    assert got == users


def test_search_users_by_username_query(repo):
    """[AC-FR1501-06] test_search_users_by_username_query."""
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="bob", email="b@x.com", role="user", active=True)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="ALI", role=None, active=None)
    assert u1 in got and u2 not in got


def test_search_users_by_email_query(repo):
    """[AC-FR1501-06] test_search_users_by_email_query."""
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="bob", email="bob@x.com", role="user", active=True)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="bob@x", role=None, active=None)
    assert u2 in got


def test_search_users_by_role(repo):
    """[AC-FR1501-06] test_search_users_by_role."""
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="admin", email="b@x.com", role="admin", active=True)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="", role="admin", active=None)
    assert u2 in got and u1 not in got


def test_search_users_by_active(repo):
    """[AC-FR1501-06] test_search_users_by_active."""
    u1 = MagicMock(username="alice", email="a@x.com", role="user", active=True)
    u2 = MagicMock(username="bob", email="b@x.com", role="user", active=False)
    repo.list_all = MagicMock(return_value=[u1, u2])
    got = repo.search_users(query="", role=None, active=False)
    assert u2 in got


def test_search_users_exception(repo):
    """[AC-FR1501-06] test_search_users_exception."""
    repo.list_all = MagicMock(side_effect=Exception("boom"))
    got = repo.search_users(query="x")
    assert got == []


def test_list_all_empty(repo):
    """[AC-FR1501-06] test_list_all_empty."""
    repo.users = MagicMock()
    repo.users.return_value = []
    got = repo.list_all()
    assert got == []


def test_list_all_with_users(repo):
    """[AC-FR1501-06] test_list_all_with_users."""
    fake_dicts = [{"id": 1, "username": "a"}, {"id": 2, "username": "b"}]
    repo.users = MagicMock()
    repo.users.return_value = iter(fake_dicts)

    # Mock _dict_to_user
    with patch.object(repo, "_dict_to_user", side_effect=lambda d: f"user-{d['username']}"):
        got = repo.list_all()
    assert got == ["user-a", "user-b"]


def test_list_all_exception(repo):
    """[AC-FR1501-06] test_list_all_exception."""
    repo.users = MagicMock(side_effect=Exception("boom"))
    got = repo.list_all()
    assert got == []


def test_verify_password(repo):
    """[AC-FR1501-06] test_verify_password."""
    with patch("quantide.web.auth.repository.User.verify_password", return_value=True):
        assert repo.verify_password("pw", "hashed") is True
    with patch("quantide.web.auth.repository.User.verify_password", return_value=False):
        assert repo.verify_password("pw", "hashed") is False


def test_dict_to_user_returns_user(repo):
    """[AC-FR1501-06] test_dict_to_user_returns_user."""
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
    """[AC-FR1501-06] If dict is already a User, returned as-is."""
    from quantide.web.auth.repository import User
    real_user = MagicMock(spec=User)
    real_user.username = "alice"
    got = repo._dict_to_user(real_user)
    assert got is real_user


from unittest.mock import patch


# ---------------------------------------------------------------------------
# get_by_id + authenticate + update + delete + delete_by_username
# ---------------------------------------------------------------------------


from quantide.web.auth.repository import User, UserRepository


@pytest.fixture
def repo(db):
    repo = UserRepository(db=db)
    repo.users = MagicMock()
    return repo


def test_get_by_id_found(repo):
    """[AC-FR1501-06] test_get_by_id_found."""
    mock_user = {"id": 1, "username": "alice", "email": "a@x.com", "active": True, "password": "h", "role": "user", "created_at": "", "last_login": ""}
    repo.users.__getitem__ = MagicMock(return_value=mock_user)
    out = repo.get_by_id(1)
    assert out is not None


def test_get_by_id_not_found(repo):
    """[AC-FR1501-06] test_get_by_id_not_found."""
    repo.users.__getitem__ = MagicMock(side_effect=Exception("not found"))
    assert repo.get_by_id(999) is None


def test_authenticate_user_not_found(repo):
    """[AC-FR1501-06] test_authenticate_user_not_found."""
    repo.users.rows_where = MagicMock(return_value=[])
    out = repo.authenticate("alice", "pw")
    assert out is None


def test_authenticate_inactive(repo):
    """[AC-FR1501-06] test_authenticate_inactive."""
    repo.users.rows_where = MagicMock(return_value=[])
    out = repo.authenticate("alice", "pw")
    assert out is None


def test_authenticate_bad_password(repo):
    """[AC-FR1501-06] test_authenticate_bad_password."""
    fake_user = MagicMock(username="alice", active=True, password="hashed", id=1, role="user", email="a@x.com")
    repo.users.rows_where = MagicMock(return_value=[fake_user])
    with patch.object(User, "verify_password", return_value=False):
        out = repo.authenticate("alice", "wrong")
    assert out is None


def test_update_success(repo):
    """[AC-FR1501-06] test_update_success."""
    repo.users.update = MagicMock()
    out = repo.update(1, email="new@x.com")
    assert out is True


def test_update_with_password_hashing(repo):
    """[AC-FR1501-06] test_update_with_password_hashing."""
    repo.users.update = MagicMock()
    with patch.object(User, "is_hashed", return_value=False), \
         patch.object(User, "get_hashed_password", return_value="hashed"):
        out = repo.update(1, password="plaintext")
    assert out is True


def test_update_exception(repo):
    """[AC-FR1501-06] test_update_exception."""
    repo.users.update = MagicMock(side_effect=Exception("boom"))
    out = repo.update(1, email="a@x.com")
    assert out is False


def test_delete_not_found(repo):
    """[AC-FR1501-06] test_delete_not_found."""
    repo.users.__getitem__ = MagicMock(side_effect=Exception("not found"))
    out = repo.delete(999)
    assert out is False


def test_delete_last_admin_protected(repo):
    """[AC-FR1501-06] test_delete_last_admin_protected."""
    repo.users.__getitem__ = MagicMock(return_value={"role": "admin", "id": 1, "username": "admin", "email": "a@x.com", "password": "h", "active": True, "created_at": "", "last_login": ""})
    repo.count_by_role = MagicMock(return_value={"admin": 1, "manager": 0, "user": 0})
    out = repo.delete(1)
    assert out is False


def test_delete_success(repo):
    """[AC-FR1501-06] test_delete_success."""
    repo.users.__getitem__ = MagicMock(return_value={"role": "user", "id": 1, "username": "u", "email": "a@x.com", "password": "h", "active": True, "created_at": "", "last_login": ""})
    repo.users.delete = MagicMock()
    out = repo.delete(1)
    assert out is True
    repo.users.delete.assert_called_once_with(1)


def test_delete_exception(repo):
    """[AC-FR1501-06] test_delete_exception."""
    repo.users.__getitem__ = MagicMock(return_value={"role": "user", "id": 1, "username": "u", "email": "a@x.com", "password": "h", "active": True, "created_at": "", "last_login": ""})
    repo.users.delete = MagicMock(side_effect=Exception("boom"))
    out = repo.delete(1)
    assert out is False


def test_delete_by_username_not_found(repo):
    """[AC-FR1501-06] test_delete_by_username_not_found."""
    repo.users.rows_where = MagicMock(return_value=[])
    out = repo.delete_by_username("alice")
    assert out is False


def test_delete_by_username_last_admin(repo):
    """[AC-FR1501-06] test_delete_by_username_last_admin."""
    repo.users.rows_where = MagicMock(return_value=[{"role": "admin", "id": 1, "username": "admin", "active": True, "password": "h", "email": "a@x.com", "created_at": "", "last_login": ""}])
    repo.count_by_role = MagicMock(return_value={"admin": 1})
    out = repo.delete_by_username("admin")
    assert out is False


def test_delete_by_username_success(repo):
    """[AC-FR1501-06] test_delete_by_username_success."""
    fake_user = {"role": "user", "id": 1, "username": "alice", "active": True, "password": "h", "email": "a@x.com", "created_at": "", "last_login": ""}
    repo.users = MagicMock()
    repo.users.return_value = [fake_user]  # __call__ result
    repo.users.delete = MagicMock()
    out = repo.delete_by_username("alice")
    assert out is True


def test_delete_by_username_exception(repo):
    """[AC-FR1501-06] test_delete_by_username_exception."""
    repo.users.rows_where = MagicMock(return_value=[{"role": "user", "id": 1, "username": "alice", "active": True, "password": "h", "email": "a@x.com", "created_at": "", "last_login": ""}])
    repo.users.delete = MagicMock(side_effect=Exception("boom"))
    out = repo.delete_by_username("alice")
    assert out is False
