from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Self, TypeVar, cast

# ruff: noqa: D205
from fasthtml.common import *
from monsterui.all import *

from quantide.config.paths import get_app_db_path

from .database import AuthDatabase
from .middleware import AuthBeforeware
from .models import User
from .repository import UserRepository
from .routes import AuthRoutes

_Route = TypeVar("_Route", bound=Callable[..., Any])


class AuthManager:
    """A class to manage user authentication and route access for fasthtml apps.  Intended to be
    modular to enable easy re-use

    Methods:
        initialize: Initialize the auth system and database
        create_beforeware: Create authentication middleware
        register_routes: Register authentication routes
        require_role: Decorator for role-based access control
        require_admin: Decorator for admin-only access
        get_user: Get user by username

    """

    _instance: ClassVar["AuthManager | None"] = None
    __initialized: bool

    def __new__(
        cls, db_path: str | Path | None = None, config: dict[str, Any] | None = None
    ) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__initialized = False
        return cast(Self, cls._instance)

    def __init__(
        self, db_path: str | Path | None = None, config: dict[str, Any] | None = None
    ) -> None:
        if self.__initialized:
            return
        self.__initialized = True
        self.config = config or {}
        if db_path is None:
            db_path = get_app_db_path()
        self.auth_db = AuthDatabase(db_path)
        self._closed = False
        self.middleware = AuthBeforeware(self, self.config)
        self.db = None
        self.routes: dict[str, Any] = {}  # Store route references
        self.user_repo: UserRepository | None = None
        self.route_handler = AuthRoutes(self)

    @staticmethod
    def get_instance() -> "AuthManager | None":
        """Get the singleton instance of AuthManager"""
        return AuthManager._instance

    def initialize(self, app: Any = None, prefix: str = "/auth") -> Any:
        """Initialise the auth system and optionally register routes

        Args:
            app: FastHTML application instance for route registration (optional)
            prefix: URL prefix for auth routes (default: /auth)
        """
        # Create tables
        self.reopen()
        self.db = self.auth_db.initialize_auth_tables()

        # Create repo to manage users
        self.user_repo = UserRepository(self.db)

        # Register auth routes if app is provided
        if app is not None:
            self.register_routes(app, prefix=prefix)
            self._prioritize_prefixed_routes(app, prefix)

        return self.db

    def rebind_database(self, db_path: str) -> None:
        """Rebind auth storage to a new sqlite file.

        Args:
            db_path: Target sqlite database path.
        """
        replacement = AuthDatabase(db_path)
        database = replacement.initialize_auth_tables()
        self.auth_db.close()
        self.auth_db = replacement
        self.db = database
        self.user_repo = UserRepository(database)
        self._closed = False

    def close(self) -> None:
        """Release auth storage after the ASGI owner has drained requests."""
        self.auth_db.close()
        self._closed = True

    def reopen(self) -> None:
        """Support a fresh app lifespan or factory after a previous clean shutdown."""
        if self._closed:
            self.rebind_database(self.auth_db.db_path)

    def _prioritize_prefixed_routes(self, app: Any, prefix: str) -> None:
        """Move auth routes ahead of catch-all mounts like `/`."""
        routes = list(getattr(app.router, "routes", []))
        prefixed = [route for route in routes if str(getattr(route, "path", "")).startswith(prefix)]
        if not prefixed:
            return
        others = [route for route in routes if route not in prefixed]
        app.router.routes[:] = prefixed + others

    def create_beforeware(self, additional_public_paths: list[str] | None = None) -> Any:
        return self.middleware.create_beforeware(additional_public_paths)

    def require_role(self, *roles: str) -> Callable[[_Route], _Route]:
        """Get role requirement decorator"""
        return self.middleware.require_role(*roles)

    def require_admin(self) -> Callable[[_Route], _Route]:
        """Get admin requirement decorator"""
        return self.middleware.require_admin()

    def get_user(self, username: str) -> User | None:
        if self.user_repo is None:
            return None
        return self.user_repo.get_by_username(username)

    def register_routes(
        self,
        app: Any,
        prefix: str = "/auth",
        include_admin: bool = False,
        allow_custom_login: bool = False,
    ) -> dict[str, Any]:
        """
        Register authentication routes with optional admin interface

        Args:
            app: FastHTML application instance
            prefix: URL prefix for auth routes (default: /auth)
            include_admin: Enable admin user management interface (default: False)
                - Adds /auth/admin dashboard
                - Adds /auth/admin/users for user management
                - Adds CRUD operations for users
            allow_custom_login: Allow custom login implementation (default: False)
                - When True, skips default login routes to allow custom implementation
                - When False, registers default login routes

        Returns:
            Dictionary of registered routes

        Example:
            # Basic auth without admin interface
            auth.register_routes(app)

            # Include admin interface for user management
            auth.register_routes(app, include_admin=True)

            # Allow custom login implementation
            auth.register_routes(app, allow_custom_login=True)
        """
        return self.route_handler.register_all(
            app,
            prefix,
            include_admin=include_admin,
            allow_custom_login=allow_custom_login,
        )
