"""Manage the durable data, factor and strategy directories."""

from typing import Any

from fasthtml.common import Button, Div, Form, Input, Label, P
from starlette.requests import Request
from starlette.responses import RedirectResponse

from quantide.config.paths import normalize_factor_dir, normalize_strategy_dir
from quantide.config.settings import get_settings
from quantide.service.init_wizard import init_wizard
from quantide.web.application import fast_app
from quantide.web.pages.system._auth import guarded_index, guarded_save
from quantide.web.pages.system._layout import render_settings_page
from quantide.web.theme import AppTheme

system_directories_app, rt = fast_app(hdrs=AppTheme.headers())


def _field(label: str, name: str, value: str, hint: str) -> Any:
    return Div(
        Label(label, fr=f"dir-{name}", cls="q-label"),
        Input(id=f"dir-{name}", name=name, value=value, required=True, cls="q-input"),
        P(hint, cls="text-xs text-gray-500 mt-1"),
        cls="mb-4",
    )


def _render(req: Request, *, error: str = "", saved: bool = False) -> Any:
    state = init_wizard.get_state(force_refresh=True)
    settings = get_settings()
    form = Form(
        _field(
            "数据存储目录",
            "data_home",
            state.app_home or settings.app_home,
            "行情数据与缓存目录。修改后新数据写入新位置。",
        ),
        _field(
            "用户因子目录",
            "factor_dir",
            state.factor_dir or normalize_factor_dir(),
            "外部因子插件目录，保存后自动发现并挂载。",
        ),
        _field(
            "用户策略目录",
            "strategy_dir",
            state.strategy_dir or normalize_strategy_dir(),
            "用户策略目录，保存后自动加入策略扫描目录。",
        ),
        P(
            "三个目录均不得指向源码仓库内部；保存时会以当前服务进程身份执行创建和写入探测。",
            cls="text-sm text-gray-600 mb-4",
        ),
        Button(
            "保存目录",
            type="submit",
            cls="q-btn q-btn--primary",
            style="width: auto; min-width: 96px;",
        ),
        action="/system/directories/save",
        method="post",
        cls="p-6 bg-white rounded-lg shadow",
    )
    return render_settings_page(
        req,
        title="工作目录",
        active="/system/directories",
        body=form,
        error=error,
        saved=saved,
        saved_message="目录已保存并通过读写校验。",
    )


def _save(form: Any) -> Any:
    state = init_wizard.get_state(force_refresh=True)
    init_wizard.save_runtime_config(
        str(form.get("data_home") or ""),
        state.app_host,
        state.app_port,
        state.app_prefix,
        factor_dir=str(form.get("factor_dir") or ""),
        strategy_dir=str(form.get("strategy_dir") or ""),
    )
    return RedirectResponse("/system/directories/?saved=1", status_code=303)


@rt("/")
async def index(req: Request) -> Any:
    return guarded_index(req, _render)


@rt("/save", methods=["POST"])
async def save(req: Request) -> Any:
    return await guarded_save(req, _render, _save)
