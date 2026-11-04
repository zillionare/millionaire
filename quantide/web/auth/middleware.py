import functools
import inspect
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Response,
)


class AuthBeforeware:
    """Authentication middleware for fastHTML"""

    def __init__(self, auth_manager, config=None):
        self.auth_manager = auth_manager
        self.config = config or {}

        # Configure paths
        login_path = "/auth/login"
        self.login_path = self.config.get("login_path", login_path)
        self.public_paths = self.config.get("public_paths", [])
        # Static files patterns
        self.static_patterns = [
            r"/favicon\.ico",
            r"/static/.*",
            r".*\.css",
            r".*\.js",
            r".*\.png",
            r".*\.jpg",
            r".*\.jpeg",
            r".*\.gif",
            r".*\.svg",
        ]

    def create_beforeware(self, additional_public_paths=None):
        """Create beforeware for fastHTML"""
        skip_patterns = self._build_skip_patterns(additional_paths=additional_public_paths)

        # Create Beforeware authentication check function
        def auth_check(req, sess):
            """Check authentication prior to check"""
            auth_username = sess.get("auth")

            # Authentication comes only from the signed session middleware.
            # A legacy remember_user cookie is client-controlled identity, not proof of login.

            if not auth_username:
                # No auth, redirect to login
                return RedirectResponse(self.login_path, status_code=303)

            # Verify user is still valid
            user = self.auth_manager.get_user(auth_username)
            if not user or not user.active:
                # Invalid user, clear session and redirect
                sess.clear()
                return RedirectResponse(self.login_path, status_code=303)

            # Add user info to request scope for route handlers
            req.scope["auth"] = auth_username
            req.scope["user"] = user
            req.scope["user.id"] = user.id
            req.scope["user_role"] = user.role
            req.scope["user_is_admin"] = user.role == "admin"

        # Return configured Beforeware
        return Beforeware(auth_check, skip=skip_patterns)

    def _build_skip_patterns(self, additional_paths=None) -> list:
        """Build list of paths to skip auth check"""
        skip = []

        # Static files
        skip.extend(self.static_patterns)

        # Auth routes
        skip.extend([self.login_path, "/auth/register", "/auth/forgot", "/auth/reset"])

        # Configured public paths
        skip.extend(self.public_paths)

        # Additional paths from caller
        if additional_paths:
            skip.extend(additional_paths)

        # Health check and api endpoints
        skip.extend(["/health", "/api/public"])

        return skip

    def require_admin(self):
        """Decorate paths requiring the admin role."""
        return self.require_role("admin")

    def require_role(self, *allowed_roles):
        """Guard synchronous and asynchronous routes before running any handler code."""

        def decorator(function):
            only_request = len(inspect.signature(function).parameters) == 1

            def invoke(request, args, kwargs):
                return function(request) if only_request else function(request, *args, **kwargs)

            def denied(request):
                user = request.scope.get("user")
                return not user or user.role not in allowed_roles

            if inspect.iscoroutinefunction(function):

                @functools.wraps(function)
                async def async_wrapper(req, *args: Any, **kwargs: Any):
                    if denied(req):
                        return Response("Forbidden", status_code=403)
                    return await invoke(req, args, kwargs)

                return async_wrapper

            @functools.wraps(function)
            def wrapper(req, *args: Any, **kwargs: Any):
                if denied(req):
                    return Response("Forbidden", status_code=403)
                return invoke(req, args, kwargs)

            return wrapper

        return decorator
