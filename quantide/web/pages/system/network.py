"""Manage the saved web listener without changing a running socket."""

from typing import Any

from fasthtml.common import H2, A, Button, Div, Form, Input, Label, P
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from quantide.config.server_address import validate_address
from quantide.service.init_wizard import init_wizard
from quantide.web.application import fast_app
from quantide.web.auth.manager import AuthManager
from quantide.web.components.navigation import SystemBreadcrumb
from quantide.web.layouts.main import MainLayout
from quantide.web.theme import AppTheme

system_network_app, rt = fast_app(hdrs=AppTheme.headers())


def _render(req: Request, *, error: str | None = "", saved: bool = False) -> Any:
    state = init_wizard.get_state(force_refresh=True)
    layout = MainLayout(title="服务访问", user=req.session.get("auth"))
    layout.set_sidebar_active("/system/network")
    layout.set_main_block(
        lambda: Div(
            SystemBreadcrumb("服务访问"),
            H2("服务访问", cls="text-2xl font-bold mb-4"),
            Div(error, role="alert", cls="text-red-700 mb-4") if error else None,
            Div("设置已保存，重启后台服务后生效。", cls="text-green-700 mb-4") if saved else None,
            Form(
                Label("监听端口", fr="app-port", cls="q-label"),
                Input(
                    id="app-port",
                    name="app_port",
                    type="number",
                    min="1",
                    max="65535",
                    value=str(state.app_port),
                    required=True,
                    cls="q-input",
                    style="max-width: 20rem;",
                ),
                Label(
                    Input(
                        name="localhost_only",
                        type="checkbox",
                        value="true",
                        checked=state.app_host == "127.0.0.1",
                    ),
                    " 只允许本机访问",
                    cls="block mt-4",
                ),
                P(
                    "取消勾选后，服务将监听所有网络接口，可从局域网访问。",
                    cls="text-sm text-gray-600 mt-2",
                ),
                P(
                    "保存后请使用菜单栏或托盘控件重启服务；端口变更后请使用新地址访问。",
                    cls="text-sm text-gray-600 mt-2",
                ),
                Button(
                    "保存设置",
                    type="submit",
                    cls="q-btn q-btn--primary mt-4",
                    style="width: auto; min-width: 96px;",
                ),
                action="/system/network/save",
                method="post",
                cls="p-6 bg-white rounded-lg shadow",
            ),
            A("返回系统维护", href="/system/", cls="text-sm text-gray-600"),
            cls="space-y-4",
        )
    )
    return layout.render(req)


def _is_admin(req: Request) -> bool:
    manager = AuthManager.get_instance()
    user = manager.get_user(req.session.get("auth", "")) if manager else None
    return bool(user and user.active and user.role == "admin")


@rt("/")
async def index(req: Request) -> Any:
    """Show saved listener settings to administrators."""
    if not _is_admin(req):
        return Response("Forbidden", status_code=403)
    return _render(req, saved=req.query_params.get("saved") == "1")


@rt("/save", methods=["POST"])
async def save(req: Request) -> Any:
    """Persist changes for the next service start."""
    if not _is_admin(req):
        return Response("Forbidden", status_code=403)
    form = await req.form()
    host = "127.0.0.1" if form.get("localhost_only") else "0.0.0.0"
    try:
        port_value = form.get("app_port")
        if port_value is not None and not isinstance(port_value, str):
            raise ValueError("Invalid port")
        host, port = validate_address(host, port_value)
        state = init_wizard.get_state(force_refresh=True)
        init_wizard.save_runtime_config(state.app_home, host, port, state.app_prefix)
    except ValueError as exc:
        return _render(req, error=str(exc))
    return RedirectResponse("/system/network/?saved=1", status_code=303)
