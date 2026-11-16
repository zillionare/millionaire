# auth/routes.py
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

from fasthtml.common import *
from fasthtml.common import (
    H1,
    H2,
    H3,
    A,
    Button,
    Card,
    Container,
    Div,
    Form,
    Grid,
    Input,
    P,
    RedirectResponse,
    Response,
    Title,
)

# Use FastHTML's plain Label for form elements to avoid MonsterUI's uk-label styling
from fasthtml.common import Label as _Label
from monsterui.all import *
from monsterui.all import (
    ButtonT,
    CardBody,
    CardHeader,
    ContainerT,
    DivFullySpaced,
)
from starlette.datastructures import UploadFile
from starlette.requests import Request

from quantide.config.branding import get_branding
from quantide.web.application import RouteRegistrar
from quantide.web.components.modal import ModalBackdrop, ModalViewport
from quantide.web.session_data import SessionData

from . import forms as auth_forms
from .forms import (
    create_forgot_password_form,
    create_login_form,
    create_profile_form,
    create_register_form,
)

if TYPE_CHECKING:
    from fasthtml.core import FastHTML

    from .manager import AuthManager
    from .models import User
    from .repository import UserRepository


def _repository(manager: "AuthManager") -> "UserRepository":
    repository = manager.user_repo
    if repository is None:
        raise RuntimeError("auth manager is not initialized")
    return repository


def _admin_flash_message(query: Mapping[str, str]) -> Any:
    from .forms import create_message_alert

    success = query.get("success")
    if success:
        messages = {
            "created": "User created successfully!",
            "updated": "User updated successfully!",
            "deleted": "User deleted successfully!",
        }
        return create_message_alert(messages.get(success, success), "success")
    error = query.get("error")
    if error:
        messages = {
            "user_not_found": "User not found.",
            "cannot_delete_self": "You cannot delete your own account.",
            "delete_failed": "Failed to delete user.",
            "update_failed": "Failed to update user.",
        }
        return create_message_alert(messages.get(error, error), "error")
    return None


def _insert_admin_alert(response: object, message: object) -> object:
    if not message or not isinstance(response, (list, tuple)):
        return response
    result = list(response)
    for item in result:
        children = getattr(item, "children", None)
        if children is not None:
            updated = list(children)
            updated.insert(1, message)
            item.children = updated
            break
    return tuple(result)


def _validated_profile_updates(
    repository: "UserRepository",
    user: "User",
    form: Mapping[str, str | UploadFile],
) -> dict[str, str]:
    """Require the existing credential and validate all fields before changing the account."""
    updates: dict[str, str] = {}
    email = auth_forms.form_text(form, "email").strip()
    if email and email != user.email:
        updates["email"] = email
    current = auth_forms.form_text(form, "current_password")
    password = auth_forms.form_text(form, "new_password")
    if not current and not password:
        return updates
    if not current:
        raise ValueError("当前密码不能为空")
    if not repository.verify_password(current, user.password or ""):
        raise ValueError("当前密码不正确")
    if password != auth_forms.form_text(form, "confirm_password"):
        raise ValueError("两次输入的新密码不一致")
    if len(password) < 8:
        raise ValueError("新密码至少需要8个字符")
    updates["password"] = password
    return updates


def _profile_error_redirect(
    prefix: str, form: Mapping[str, str | UploadFile], message: str
) -> RedirectResponse:
    path = "modal/reset-password" if auth_forms.form_text(form, "modal") == "1" else "profile"
    return RedirectResponse(f"{prefix}/{path}?error={message}", status_code=303)


def _create_admin_dashboard_handler(
    self: "AuthRoutes", prefix: str, rt: RouteRegistrar
) -> Callable[..., object]:
    """Create the admin dashboard route with explicit dependencies."""

    @rt(f"{prefix}/admin")
    @self.auth.require_admin()
    def admin_dashboard(req: Request) -> Any:

        # Get user statistics
        user_counts = _repository(self.auth).count_by_role()
        total_users = sum(user_counts.values())

        return Title("Admin Dashboard"), Container(
            DivFullySpaced(
                H1("Admin Dashboard"),
                A("← Back to Main Dashboard", href="/", cls=ButtonT.secondary),
            ),
            Grid(
                Card(
                    CardHeader(H3("Total Users")),
                    CardBody(
                        H2(str(total_users), cls="text-3xl font-bold"),
                        P("Registered users", cls="text-muted-foreground"),
                    ),
                ),
                Card(
                    CardHeader(H3("Admins")),
                    CardBody(
                        H2(
                            str(user_counts.get("admin", 0)),
                            cls="text-3xl font-bold text-gray-600",
                        ),
                        P("Admin accounts", cls="text-muted-foreground"),
                    ),
                ),
                Card(
                    CardHeader(H3("Managers")),
                    CardBody(
                        H2(
                            str(user_counts.get("manager", 0)),
                            cls="text-3xl font-bold text-[#e41815]",
                        ),
                        P("Manager accounts", cls="text-muted-foreground"),
                    ),
                ),
                Card(
                    CardHeader(H3("Users")),
                    CardBody(
                        H2(
                            str(user_counts.get("user", 0)),
                            cls="text-3xl font-bold text-gray-600",
                        ),
                        P("Regular users", cls="text-muted-foreground"),
                    ),
                ),
                cols=1,
                cols_md=2,
                cols_lg=4,
            ),
            Card(
                CardHeader(H3("Quick Actions")),
                CardBody(
                    Grid(
                        A(
                            "Manage Users",
                            href=f"{prefix}/admin/users",
                            cls=ButtonT.primary,
                        ),
                        A(
                            "Create New User",
                            href=f"{prefix}/admin/users/create",
                            cls=ButtonT.secondary,
                        ),
                        A(
                            "View Profile",
                            href=f"{prefix}/profile",
                            cls=ButtonT.secondary,
                        ),
                        A(
                            "System Settings",
                            href="#",
                            cls=ButtonT.secondary + " opacity-50 cursor-not-allowed",
                        ),
                        cols=2,
                        cols_md=4,
                    )
                ),
                cls="mt-6",
            ),
            cls=ContainerT.xl,
        )

    return admin_dashboard


def _create_admin_users_list_with_messages_handler(
    self: "AuthRoutes", original_list: Callable[[Request], object], rt: RouteRegistrar, prefix: str
) -> Callable[..., object]:
    """Register the admin list with messages while retaining its role guard."""

    @rt(f"{prefix}/admin/users")
    @self.auth.require_admin()
    def admin_users_list_with_messages(req: Request) -> Any:
        return _insert_admin_alert(original_list(req), _admin_flash_message(req.query_params))

    return admin_users_list_with_messages


def _create_register_page_handler(prefix: str, rt: RouteRegistrar) -> Callable[..., object]:
    """Create the register page route with explicit dependencies."""

    @rt(f"{prefix}/register", methods=["GET"])
    def register_page(req: Request) -> Any:
        error = req.query_params.get("error")
        return Title("Register"), Container(
            create_register_form(error=error, action=f"{prefix}/register")
        )

    return register_page


def _create_register_submit_handler(
    self: "AuthRoutes", prefix: str, rt: RouteRegistrar
) -> Callable[..., object]:
    """Create the register submit route with explicit dependencies."""

    @rt(f"{prefix}/register", methods=["POST"])
    async def register_submit(req: Request, sess: SessionData) -> Any:
        form = await req.form()
        username = auth_forms.form_text(form, "username").strip()
        email = auth_forms.form_text(form, "email").strip()
        password = auth_forms.form_text(form, "password")
        confirm = auth_forms.form_text(form, "confirm_password")
        accept_terms = auth_forms.form_text(form, "accept_terms") == "on"

        if not accept_terms:
            return RedirectResponse(f"{prefix}/register?error=terms_required", status_code=303)

        # Validation
        if password != confirm:
            return RedirectResponse(f"{prefix}/register?error=password_mismatch", status_code=303)

        if password != confirm:
            return RedirectResponse(f"{prefix}/register?error=password_mismatch", status_code=303)

        # Check if user exists
        if _repository(self.auth).get_by_username(username):
            return RedirectResponse(f"{prefix}/register?error=username_taken", status_code=303)

        # Create user
        try:
            user = _repository(self.auth).create(username, email, password)
            if user:
                # Auto-login after registration
                sess["auth"] = str(user.username or "")
                sess["user_id"] = str(user.id or "")
                sess["role"] = str(user.role or "")
                return RedirectResponse("/", status_code=303)
        except Exception as e:
            print(f"Registration error: {e}")
            return RedirectResponse(f"{prefix}/register?error=creation_failed", status_code=303)

        return RedirectResponse(f"{prefix}/register?error=creation_failed", status_code=303)

    return register_submit


def _create_profile_page_handler(prefix: str, rt: RouteRegistrar) -> Callable[..., object]:
    """Create the profile page route with explicit dependencies."""

    @rt(f"{prefix}/profile", methods=["GET"])
    def profile_page(req: Request) -> Any:
        user = req.scope["user"]  # Added by beforeware
        success = req.query_params.get("success")
        error = req.query_params.get("error")
        return Title("个人设置"), create_profile_form(
            user=user, success=success, error=error, action=f"{prefix}/profile"
        )

    return profile_page


def _create_reset_password_modal_handler(prefix: str, rt: RouteRegistrar) -> Callable[..., object]:
    """Create the reset password modal route with explicit dependencies."""

    @rt(f"{prefix}/modal/reset-password", methods=["GET"])
    def reset_password_modal(req: Request) -> Any:
        error = req.query_params.get("error")

        # Simple form for the modal
        form_content = Form(
            Input(type="hidden", name="modal", value="1"),
            Div(
                _Label("当前密码", cls="block text-sm font-medium text-gray-700 mb-1"),
                Input(
                    type="password",
                    name="current_password",
                    required=True,
                    cls="w-full h-10 px-3 rounded-md border border-gray-300",
                ),
                cls="mb-4",
            ),
            Div(
                _Label("新密码", cls="block text-sm font-medium text-gray-700 mb-1"),
                Input(
                    type="password",
                    name="new_password",
                    required=True,
                    cls="w-full h-10 px-3 rounded-md border border-gray-300",
                ),
                cls="mb-4",
            ),
            Div(
                _Label("确认新密码", cls="block text-sm font-medium text-gray-700 mb-1"),
                Input(
                    type="password",
                    name="confirm_password",
                    required=True,
                    cls="w-full h-10 px-3 rounded-md border border-gray-300",
                ),
                cls="mb-4",
            ),
            Div(
                Div(error, cls="text-sm text-red-500 mb-4") if error else None,
                Div(
                    Button(
                        "取消",
                        type="button",
                        cls=ButtonT.ghost,
                        onclick="document.getElementById('global-reset-password-modal-container').innerHTML=''",
                    ),
                    Button("确认修改", type="submit", cls=ButtonT.primary),
                    cls="flex justify-end gap-2",
                ),
            ),
            hx_post=f"{prefix}/profile",
            hx_target="#global-reset-password-modal-container",
        )

        return Div(
            ModalBackdrop(),
            ModalViewport(
                Div(
                    Div(
                        H3("重设密码", cls="text-lg font-medium leading-6 text-gray-900"),
                        cls="px-4 py-5 sm:px-6 border-b border-gray-200",
                    ),
                    Div(form_content, cls="px-4 py-5 sm:p-6"),
                    cls=(
                        "inline-block transform overflow-hidden rounded-lg "
                        "bg-white text-left align-bottom shadow-xl "
                        "transition-all sm:my-8 sm:w-full sm:max-w-lg "
                        "sm:align-middle"
                    ),
                ),
                "flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0",
            ),
            id="global-reset-password-modal",
            cls="relative z-[100]",
        )

    return reset_password_modal


def _create_profile_submit_handler(
    self: "AuthRoutes", prefix: str, rt: RouteRegistrar
) -> Callable[..., object]:
    """Register profile updates with validation before a single repository write."""

    @rt(f"{prefix}/profile", methods=["POST"])
    async def profile_submit(req: Request) -> Any:
        user = req.scope["user"]
        form = await req.form()
        try:
            updates = _validated_profile_updates(_repository(self.auth), user, form)
            if updates:
                _repository(self.auth).update(user.id, **updates)
            if "password" in updates:
                req.scope["session"].clear()
                target = f"{prefix}/login?success=password_changed"
                return (
                    Response(headers={"HX-Redirect": target})
                    if auth_forms.form_text(form, "modal") == "1"
                    else RedirectResponse(target, status_code=303)
                )
            return RedirectResponse(f"{prefix}/profile?success=1", status_code=303)
        except ValueError as exc:
            return _profile_error_redirect(prefix, form, str(exc))
        except Exception:
            return _profile_error_redirect(prefix, form, "保存失败")

    return profile_submit


class AuthRoutes:
    """Handles route registration for auth system"""

    def __init__(self, auth_manager: "AuthManager") -> None:
        self.auth = auth_manager
        self.routes: dict[str, Callable[..., object]] = {}

    def register_all(
        self,
        app: "FastHTML",
        prefix: str = "/auth",
        include_admin: bool = False,
        allow_custom_login: bool = False,
    ) -> dict[str, Callable[..., object]]:
        """Register all auth routes with optional admin interface"""
        rt: RouteRegistrar = app.route

        # Handle success/error messages for admin operations
        if include_admin:
            # Import AdminRoutes only when needed
            from .admin_routes import AdminRoutes

            admin_handler = AdminRoutes(self.auth)

        # Register each route group
        # Only register default login routes if custom login is not allowed
        if allow_custom_login:
            # Skip login routes to allow custom implementation
            self._register_logout_route(rt, prefix)
            self._register_profile_route(rt, prefix)
        else:
            # Register default login routes
            self._register_login_routes(rt, prefix)
            self._register_logout_route(rt, prefix)
            self._register_profile_route(rt, prefix)

        if self.auth.config.get("allow_registration"):
            self._register_registration_routes(rt, prefix)

        if self.auth.config.get("allow_password_reset"):
            self._register_password_reset_routes(rt, prefix)

        # Register admin routes if requested
        if include_admin:
            admin_routes = admin_handler.register_admin_routes(app, f"{prefix}/admin")
            self.routes.update(admin_routes)

            # Add admin dashboard route
            admin_dashboard = _create_admin_dashboard_handler(self, prefix, rt)

            self.routes["admin_dashboard"] = admin_dashboard

            # Update the user list route to show success/error messages
            original_list = self.routes.get("admin_users_list")
            if original_list:
                admin_users_list_with_messages = _create_admin_users_list_with_messages_handler(
                    self, original_list, rt, prefix
                )

                self.routes["admin_users_list"] = admin_users_list_with_messages

        return self.routes

    def _register_login_routes(self, rt: RouteRegistrar, prefix: str) -> None:
        """Register login routes"""

        # Login routes
        @rt(f"{prefix}/login", methods=["GET"])
        def login_page(req: Request) -> Any:
            error = req.query_params.get("error")
            # Get redirect destination from query params
            redirect_to = req.query_params.get("redirect_to", "/")
            return Title(f"{get_branding().product_name} 登录"), (
                create_login_form(error=error, action=f"{prefix}/login", redirect_to=redirect_to)
            )

        self.routes["login_page"] = login_page

        @rt(f"{prefix}/login", methods=["POST"])
        async def login_submit(req: Request, sess: SessionData) -> Any:
            form = await req.form()
            username = auth_forms.form_text(form, "username").strip() or "admin"
            password = auth_forms.form_text(form, "password")
            remember_me = auth_forms.form_text(form, "remember_me") == "on"

            # Authenticate
            user = _repository(self.auth).authenticate(username, password)

            if user:
                # Set session
                sess["auth"] = str(user.username or "")
                sess["user_id"] = str(user.id or "")
                sess["role"] = str(user.role or "")

                redirect_url = auth_forms.form_text(form, "redirect_to", "/")
                response = RedirectResponse(redirect_url, status_code=303)

                response.delete_cookie("remember_user")
                if remember_me:
                    sess["remember_me"] = True
                else:
                    sess.pop("remember_me", None)

                return response

            # On failure, preserve the redirect_to parameter
            redirect_to = auth_forms.form_text(form, "redirect_to", "/")
            error_url = f"{prefix}/login?error=invalid"
            if redirect_to != "/":
                error_url += f"&redirect_to={redirect_to}"
            return RedirectResponse(error_url, status_code=303)

        self.routes["login_submit"] = login_submit

    def _register_logout_route(self, rt: RouteRegistrar, prefix: str) -> None:
        @rt(f"{prefix}/logout")
        def logout(sess: SessionData) -> Any:
            cast(dict[str, Any], sess).clear()
            return RedirectResponse(f"{prefix}/login", status_code=303)

        self.routes["logout"] = logout

    def _register_registration_routes(self, rt: RouteRegistrar, prefix: str) -> None:

        # Optional: Register route
        if self.auth.config.get("allow_registration", False):
            register_page = _create_register_page_handler(prefix, rt)

            register_submit = _create_register_submit_handler(self, prefix, rt)

            self.routes["register_page"] = register_page
            self.routes["register_submit"] = register_submit

    def _register_password_reset_routes(self, rt: RouteRegistrar, prefix: str) -> None:
        # Optional: Password reset route
        if self.auth.config.get("allow_password_reset", False):

            @rt(f"{prefix}/forgot", methods=["GET"])
            def forgot_page(req: Request) -> Any:
                error = req.query_params.get("error")
                success = req.query_params.get("success")
                return Title("Forgot Password"), create_forgot_password_form(
                    error=error, success=success, action=f"{prefix}/forgot"
                )

            @rt(f"{prefix}/forgot", methods=["POST"])
            async def forgot_submit(req: Request) -> Any:
                form = await req.form()
                auth_forms.form_text(form, "email").strip()

                # TODO: Implement actual password reset logic
                # For now, just show success message
                return RedirectResponse(f"{prefix}/forgot?success=sent", status_code=303)

            self.routes["forgot_password"] = forgot_page
            self.routes["forgot_submit"] = forgot_submit

    def _register_profile_route(self, rt: RouteRegistrar, prefix: str) -> None:
        # Register route to a profile form
        profile_page = _create_profile_page_handler(prefix, rt)

        _create_reset_password_modal_handler(prefix, rt)

        profile_submit = _create_profile_submit_handler(self, prefix, rt)

        self.routes["profile_page"] = profile_page
        self.routes["profile_submit"] = profile_submit
