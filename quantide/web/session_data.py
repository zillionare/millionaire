"""Typed shape of the signed-session payload used by FastHTML routes."""

from typing import TypedDict


class SessionData(TypedDict, total=False):
    """Session keys written by authentication and account selection."""

    auth: str
    initializing: bool
    active_account_kind: str
    active_account_id: str
    user_id: int | str
    role: str
    remember_me: bool
