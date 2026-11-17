"""SQLite persistence for AI factor studio sessions and messages."""

from __future__ import annotations

import json
import uuid
from typing import Any

from quantide.core.market_time import market_now
from quantide.data.sqlite import db

SESSION_TABLE = "ai_studio_sessions"
MESSAGE_TABLE = "ai_studio_messages"
SESSION_STATUSES = {"idle", "running", "cancelling", "cancelled", "failed", "completed"}
MESSAGE_ROLES = {"system", "user", "assistant", "tool"}


def _now() -> str:
    return market_now().isoformat(timespec="seconds")


def ensure_ai_studio_tables() -> None:
    """Create the two durable studio tables if they do not exist."""
    sessions = db[SESSION_TABLE]
    sessions.create(
        {
            "session_id": str,
            "title": str,
            "active_factor_id": str,
            "status": str,
            "created_at": str,
            "updated_at": str,
        },
        pk="session_id",
        if_not_exists=True,
    )
    messages = db[MESSAGE_TABLE]
    messages.create(
        {
            "message_id": str,
            "session_id": str,
            "role": str,
            "content": str,
            "step_cards_json": str,
            "run_id": str,
            "created_at": str,
        },
        pk="message_id",
        if_not_exists=True,
    )
    messages.create_index(["session_id", "created_at"], if_not_exists=True)


def create_session(
    title: str = "新的 AI 因子会话", *, active_factor_id: str = ""
) -> dict[str, Any]:
    ensure_ai_studio_tables()
    stamp = _now()
    row = {
        "session_id": uuid.uuid4().hex[:16],
        "title": str(title or "新的 AI 因子会话").strip()[:80],
        "active_factor_id": str(active_factor_id or "").strip(),
        "status": "idle",
        "created_at": stamp,
        "updated_at": stamp,
    }
    db[SESSION_TABLE].insert(row)
    return row


def list_sessions(*, limit: int = 30) -> list[dict[str, Any]]:
    ensure_ai_studio_tables()
    rows = db[SESSION_TABLE].rows_where(order_by="updated_at desc", limit=max(1, int(limit)))
    return [dict(row) for row in rows]


def get_session(session_id: str) -> dict[str, Any] | None:
    ensure_ai_studio_tables()
    row = db[SESSION_TABLE].get(str(session_id))
    return dict(row) if row else None


def update_session(session_id: str, **fields: Any) -> dict[str, Any] | None:
    ensure_ai_studio_tables()
    allowed = {"title", "active_factor_id", "status"}
    payload = {key: value for key, value in fields.items() if key in allowed}
    if "status" in payload and payload["status"] not in SESSION_STATUSES:
        raise ValueError(f"非法 AI 会话状态: {payload['status']}")
    payload["updated_at"] = _now()
    if db[SESSION_TABLE].get(str(session_id)) is None:
        return None
    db[SESSION_TABLE].update(str(session_id), payload)
    return get_session(session_id)


def append_message(
    session_id: str,
    role: str,
    content: str,
    *,
    step_cards: list[dict[str, Any]] | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    ensure_ai_studio_tables()
    if role not in MESSAGE_ROLES:
        raise ValueError(f"非法 AI 消息角色: {role}")
    if get_session(session_id) is None:
        raise KeyError(f"AI 会话不存在: {session_id}")
    row = {
        "message_id": uuid.uuid4().hex,
        "session_id": str(session_id),
        "role": role,
        "content": str(content or ""),
        "step_cards_json": json.dumps(step_cards or [], ensure_ascii=False),
        "run_id": str(run_id or ""),
        "created_at": _now(),
    }
    db[MESSAGE_TABLE].insert(row)
    update_session(session_id)
    return row


def list_messages(session_id: str) -> list[dict[str, Any]]:
    ensure_ai_studio_tables()
    rows = db[MESSAGE_TABLE].rows_where(
        "session_id = ?", (str(session_id),), order_by="created_at, rowid"
    )
    messages = []
    for row in rows:
        item = dict(row)
        try:
            cards = json.loads(item.get("step_cards_json") or "[]")
        except ValueError:
            cards = []
        item["step_cards"] = cards if isinstance(cards, list) else []
        item.pop("step_cards_json", None)
        messages.append(item)
    return messages


def latest_assistant_cards(session_id: str) -> list[dict[str, Any]]:
    for message in reversed(list_messages(session_id)):
        if message.get("role") == "assistant" and message.get("step_cards"):
            return list(message["step_cards"])
    return []


__all__ = [
    "MESSAGE_TABLE",
    "SESSION_TABLE",
    "append_message",
    "create_session",
    "ensure_ai_studio_tables",
    "get_session",
    "latest_assistant_cards",
    "list_messages",
    "list_sessions",
    "update_session",
]
