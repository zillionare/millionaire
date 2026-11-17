"""Small admin guards shared by system settings pages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from quantide.web.auth.manager import AuthManager


def is_admin(req: Request) -> bool:
    manager = AuthManager.get_instance()
    user = manager.get_user(req.session.get("auth", "")) if manager else None
    return bool(user and user.active and user.role == "admin")


def require_admin(req: Request) -> Response | None:
    if is_admin(req):
        return None
    return Response("Forbidden", status_code=403)


def guarded_index(req: Request, render: Callable[..., Any]) -> Any:
    denied = require_admin(req)
    if denied is not None:
        return denied
    return render(req, saved=req.query_params.get("saved") == "1")


async def guarded_save(
    req: Request,
    render: Callable[..., Any],
    action: Callable[[Any], Any],
) -> Any:
    denied = require_admin(req)
    if denied is not None:
        return denied
    form = await req.form()
    try:
        return action(form)
    except ValueError as exc:
        return render(req, error=str(exc))


__all__ = ["guarded_index", "guarded_save", "is_admin", "require_admin"]
