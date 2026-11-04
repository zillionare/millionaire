# auth/forms.py
import fasthtml.common as fh
from fasthtml.common import *
from monsterui.all import *

from quantide.config.branding import get_branding


def _login_error_message(error):
    messages = {
        "invalid": "密码错误，请重新输入。",
        "inactive": "当前账号已停用，请联系管理员。",
        "system": "系统暂时不可用，请稍后再试。",
    }
    return messages.get(error)


def _login_field(label_cn, label_en, field_id, name, placeholder, field_type="text"):
    return Div(
        fh.Label(
            f"{label_cn}/{label_en}",
            fr=field_id,
            cls="qt-login-label",
        ),
        fh.Input(
            id=field_id,
            name=name,
            type=field_type,
            placeholder=placeholder,
            required=True,
            autofocus=field_id == "password",
            autocomplete="current-password" if field_type == "password" else "username",
            cls="qt-login-input",
        ),
        cls="qt-login-field",
    )


def _brand_emblem():
    return Div(Img(src="/static/logo.png", alt="Quantide"), cls="qt-emblem")


def create_login_form(error=None, action="/auth/login", redirect_to="/"):
    """Create branded login form while preserving auth behavior."""
    error_message = _login_error_message(error)
    branding = get_branding()

    return Div(
        Link(rel="stylesheet", href="/static/login.css?v=3"),
        Div(
            Div(
                Div(
                    Div(
                        Div("QUANTIDE / QUANTITATIVE INVESTING", cls="qt-brand-tagline"),
                        cls="qt-brand-mark",
                    ),
                    Div(Span("投资如山岳般古老，"), Span("但工具常新"), cls="qt-brand-slogan"),
                    Div(
                        Div(branding.product_name),
                        cls="qt-brand-footer",
                    ),
                    cls="qt-login-brand",
                ),
                Div(
                    Div("WELCOME BACK", cls="qt-login-eyebrow"),
                    H2("欢迎回来", cls="qt-login-title"),
                    P(
                        f"登录 {branding.product_name}，继续您的量化之旅。",
                        cls="qt-login-description",
                    ),
                    Form(
                        Input(type="hidden", name="redirect_to", value=redirect_to),
                        Alert(error_message, cls="qt-login-error") if error_message else None,
                        _login_field(
                            "密码",
                            "Password",
                            "password",
                            "password",
                            "请输入密码",
                            field_type="password",
                        ),
                        fh.Label(
                            fh.Input(type="checkbox", name="remember_me", value="on"),
                            Span("记住我/Remember me"),
                            cls="qt-login-remember",
                        ),
                        Button("登录", type="submit", cls="qt-login-button"),
                        method="post",
                        action=action,
                        cls="qt-login-form",
                    ),
                    cls="qt-login-panel",
                ),
                _brand_emblem(),
                cls="qt-login-card",
            ),
            cls="qt-login-page",
        ),
    )


def create_register_form(error=None, action="/auth/register"):
    """Create registration form component with same style as login"""
    error_message = None
    if error == "username_taken":
        error_message = "Username already taken. Please choose another."
    elif error == "email_taken":
        error_message = "Email already registered. Please sign in or use another email."
    elif error == "password_mismatch":
        error_message = "Passwords do not match. Please try again."
    elif error == "password_weak":
        error_message = "Password must be at least 8 characters long."
    elif error == "invalid_email":
        error_message = "Please enter a valid email address."
    elif error == "creation_failed":
        error_message = "Failed to create account. Please try again."
    elif error == "terms_required":  # NEW ERROR MESSAGE
        error_message = "You must accept the Terms and Conditions to register."

    return DivCentered(
        Card(
            CardHeader(
                H3("Create Account", cls="text-center"),
                Subtitle("Join us today", cls="text-center"),
            ),
            CardBody(
                Alert(error_message, cls=AlertT.error) if error_message else None,
                Form(
                    LabelInput(
                        "Username",
                        id="username",
                        name="username",
                        placeholder="Choose a username",
                        required=True,
                        autofocus=True,
                        pattern="[a-zA-Z0-9_]{3,20}",
                        title="3-20 characters, letters, numbers and underscore only",
                    ),
                    LabelInput(
                        "Email",
                        id="email",
                        name="email",
                        type="email",
                        placeholder="your@email.com",
                        required=True,
                    ),
                    LabelInput(
                        "Password",
                        id="password",
                        name="password",
                        type="password",
                        placeholder="Choose a strong password (8+ characters)",
                        required=True,
                        minlength=8,
                    ),
                    LabelInput(
                        "Confirm Password",
                        id="confirm_password",
                        name="confirm_password",
                        type="password",
                        placeholder="Re-enter your password",
                        required=True,
                        minlength=8,
                    ),
                    Div(
                        Label(
                            CheckboxX(name="accept_terms", selected=False, required=True),
                            Span(" I accept the Terms and Conditions", cls="ml-2"),
                            cls="flex items-center text-sm cursor-pointer",
                        ),
                        cls="mb-4",
                    ),
                    Button("Create Account", type="submit", cls=(ButtonT.primary, "w-full")),
                    method="post",
                    action=action,
                ),
            ),
            footer=DivCentered(
                P(
                    "Already have an account? ",
                    A("Sign In", href="/auth/login", cls="font-medium hover:underline"),
                    cls="text-sm text-muted-foreground",
                ),
                cls="p-4",
            ),
            cls="w-full max-w-md shadow-lg",
        ),
        cls="min-h-screen flex items-center justify-center p-4",
    )


def create_forgot_password_form(error=None, success=None, action="/auth/forgot"):
    """Create password reset request form with same style"""
    error_message = None
    success_message = None

    if error == "user_not_found":
        error_message = "No account found with that email address."
    elif error == "send_failed":
        error_message = "Failed to send reset email. Please try again."

    if success == "sent":
        success_message = "Password reset instructions have been sent to your email."

    return DivCentered(
        Card(
            CardHeader(
                H3("Reset Password", cls="text-center"),
                Subtitle("We'll send you reset instructions", cls="text-center"),
            ),
            CardBody(
                Alert(error_message, cls=AlertT.error) if error_message else None,
                Alert(success_message, cls=AlertT.success) if success_message else None,
                (
                    Form(
                        LabelInput(
                            "Email Address",
                            id="email",
                            name="email",
                            type="email",
                            placeholder="your@email.com",
                            required=True,
                            autofocus=True,
                        ),
                        Button(
                            "Send Reset Link",
                            type="submit",
                            cls=(ButtonT.primary, "w-full"),
                        ),
                        method="post",
                        action=action,
                    )
                    if not success_message
                    else Div(
                        P(
                            "Check your email for further instructions.",
                            cls="text-center text-muted-foreground",
                        )
                    )
                ),
                DivCentered(
                    A(
                        "← Back to Sign In",
                        href="/auth/login",
                        cls=(ButtonT.secondary, "mt-4"),
                    )
                ),
            ),
            cls="w-full max-w-md shadow-lg",
        ),
        cls="min-h-screen flex items-center justify-center p-4",
    )


def create_reset_password_form(token, error=None, action="/auth/reset"):
    """Create password reset form (after clicking email link)"""
    error_message = None

    if error == "invalid_token":
        error_message = "Invalid or expired reset token. Please request a new one."
    elif error == "password_mismatch":
        error_message = "Passwords do not match. Please try again."
    elif error == "password_weak":
        error_message = "Password must be at least 8 characters long."

    return DivCentered(
        Card(
            CardHeader(
                H3("Choose New Password", cls="text-center"),
                Subtitle("Enter your new password below", cls="text-center"),
            ),
            CardBody(
                Alert(error_message, cls=AlertT.error) if error_message else None,
                Form(
                    Input(type="hidden", name="token", value=token),
                    LabelInput(
                        "New Password",
                        id="password",
                        name="password",
                        type="password",
                        placeholder="Enter new password (8+ characters)",
                        required=True,
                        minlength=8,
                        autofocus=True,
                    ),
                    LabelInput(
                        "Confirm New Password",
                        id="confirm_password",
                        name="confirm_password",
                        type="password",
                        placeholder="Re-enter new password",
                        required=True,
                        minlength=8,
                    ),
                    Button("Reset Password", type="submit", cls=(ButtonT.primary, "w-full")),
                    method="post",
                    action=action,
                ),
            ),
            footer=DivCentered(
                P(
                    "Remember your password? ",
                    A("Sign In", href="/auth/login", cls="font-medium hover:underline"),
                    cls="text-sm text-muted-foreground",
                ),
                cls="p-4",
            ),
            cls="w-full max-w-md shadow-lg",
        ),
        cls="min-h-screen flex items-center justify-center p-4",
    )


def create_profile_form(user, success=None, error=None, action="/auth/profile"):
    """Create profile edit form for logged-in users"""
    return Container(
        DivFullySpaced(
            H1("个人设置"),
            A("返回首页", href="/", cls=ButtonT.secondary),
        ),
        Grid(
            Card(
                CardHeader(H3("账户信息")),
                CardBody(
                    (Alert("个人设置已更新。", cls=AlertT.success) if success else None),
                    Alert(error, cls=AlertT.error) if error else None,
                    Form(
                        Grid(
                            LabelInput(
                                "用户名",
                                value=user.username,
                                disabled=True,
                                cls="bg-muted",
                            ),
                            user_email_input(user),
                            cols=1,
                            cols_md=2,
                        ),
                        Div(
                            Hr(cls="my-6"),
                            H4("重设密码", cls="text-lg font-semibold mb-2"),
                            P(
                                "如需修改登录密码，请先输入当前密码。",
                                cls="mb-4 text-sm text-muted-foreground",
                            ),
                            LabelInput(
                                "当前密码",
                                name="current_password",
                                type="password",
                                placeholder="请输入当前密码",
                            ),
                            Grid(
                                LabelInput(
                                    "新密码",
                                    name="new_password",
                                    type="password",
                                    placeholder="请输入不少于 8 位的新密码",
                                    minlength=8,
                                ),
                                LabelInput(
                                    "确认新密码",
                                    name="confirm_password",
                                    type="password",
                                    placeholder="请再次输入新密码",
                                    minlength=8,
                                ),
                                cols=1,
                                cols_md=2,
                            ),
                            id="password-settings",
                        ),
                        DivRAligned(
                            Button("保存更改", type="submit", cls=ButtonT.primary),
                            cls="mt-6",
                        ),
                        method="post",
                        action=action,
                    ),
                ),
            ),
            Card(
                CardHeader(H3("账号详情")),
                CardBody(
                    Div(
                        InfoRow("用户名", user.username),
                        InfoRow("角色", user.role.title()),
                        InfoRow("状态", "启用" if user.active else "停用"),
                        InfoRow(
                            "创建时间",
                            user.created_at[:10] if user.created_at else "未知",
                        ),
                        InfoRow(
                            "最近登录",
                            user.last_login[:10] if user.last_login else "尚未登录",
                        ),
                        cls="space-y-3",
                    )
                ),
            ),
            cols=1,
            cols_lg=2,
        ),
        cls=ContainerT.xl,
    )


def InfoRow(label, value):
    """Render info display in profile"""
    return DivFullySpaced(
        Span(label, cls="font-medium"), Span(str(value), cls="text-muted-foreground")
    )


# Utility function for consistent error/success messaging
def create_message_alert(message, type="info"):
    """Create consistent alert messages"""
    alert_class = {
        "error": AlertT.error,
        "success": AlertT.success,
        "warning": AlertT.warning,
        "info": AlertT.info,
    }.get(type, AlertT.info)

    return Alert(message, cls=alert_class)


def user_email_input(user, label="邮箱"):
    return LabelInput(label, name="email", type="email", value=user.email, required=True)
