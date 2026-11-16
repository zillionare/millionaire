"""Apply signed-session authentication to direct routes and mounted applications."""

from typing import Any

from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from quantide.service.init_wizard import init_wizard
from quantide.web.auth.manager import AuthManager


class AuthGuard:
    """Protect every mounted route and websocket after session decoding."""

    def __init__(self, app: ASGIApp, auth: AuthManager) -> None:
        self.app = app
        self.auth = auth

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        session = scope.get("session", {})
        if self._public(path, session):
            return await self.app(scope, receive, send)
        user = self.auth.get_user(session.get("auth", ""))
        if not user or not user.active:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 4401})
            response = (
                RedirectResponse("/auth/login", status_code=303)
                if scope.get("method") == "GET"
                else JSONResponse({"error": "请先登录"}, status_code=401)
            )
            return await response(scope, receive, send)
        if path.startswith("/init-wizard") and user.role != "admin":
            response = JSONResponse({"error": "需要管理员权限"}, status_code=403)
            return await response(scope, receive, send)
        scope.update(user=user, user_role=user.role, user_is_admin=user.role == "admin")
        return await self.app(scope, receive, send)

    @staticmethod
    def _public(path: str, session: dict[str, Any]) -> bool:
        if path in {"/api/health", "/favicon.ico", "/auth/login"} or path.startswith("/static/"):
            return True
        if path == "/init-wizard" or path.startswith("/init-wizard/"):
            if not init_wizard.is_initialized():
                session["initializing"] = True
                return True
            return path in {"/init-wizard/complete", "/init-wizard/sync-progress"} and bool(
                session.get("initializing")
            )
        return False
