"""System maintenance page for the optional AI assistant settings."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Button, Div, Form, P
from starlette.requests import Request
from starlette.responses import RedirectResponse

from quantide.service.ai_assistant import (
    AIAssistantConfig,
    config_from_form,
    load_ai_assistant_config,
    public_view,
    save_ai_assistant_config,
    test_ai_connection,
)
from quantide.web.application import fast_app
from quantide.web.pages.ai_config_views import (
    AI_FORM_FIELDS,
    ai_config_fields,
    connectivity_result_view,
)
from quantide.web.pages.system._auth import guarded_index, guarded_save, require_admin
from quantide.web.pages.system._layout import render_settings_page
from quantide.web.theme import AppTheme

system_ai_app, rt = fast_app(hdrs=AppTheme.headers())


def _config_from_form(form: Any) -> AIAssistantConfig:
    values = {
        "provider_preset": form.get(AI_FORM_FIELDS["provider"]),
        "base_url": form.get(AI_FORM_FIELDS["base_url"]),
        "model": form.get(AI_FORM_FIELDS["model"]),
        "api_key": form.get(AI_FORM_FIELDS["api_key"]),
        "timeout_seconds": form.get(AI_FORM_FIELDS["timeout"]),
        "max_repair_rounds": form.get(AI_FORM_FIELDS["repair_rounds"]),
        "max_tool_steps": form.get(AI_FORM_FIELDS["tool_steps"]),
    }
    return config_from_form(values, existing=load_ai_assistant_config())


def _render(req: Request, *, error: str = "", saved: bool = False) -> Any:
    view = public_view()
    form = Form(
        ai_config_fields(view),
        Div(
            Button("保存 AI 配置", type="submit", cls="q-btn q-btn--primary"),
            Button(
                "测试连接",
                type="button",
                cls="q-btn ml-2",
                hx_post="/system/ai/test",
                hx_include="closest form",
                hx_target="#ai-system-result",
                hx_swap="innerHTML",
            ),
            Div(id="ai-system-result", cls="mt-2"),
            P(
                "保存后打开 /factors/studio 即可开始对话。未配置也不会影响因子、回测等非 AI 功能。",
                cls="text-sm text-gray-500 mt-2",
            ),
        ),
        action="/system/ai/save",
        method="post",
        cls="p-6 bg-white rounded-lg shadow",
    )
    return render_settings_page(
        req,
        title="AI 助手配置",
        active="/system/ai",
        body=form,
        error=error,
        saved=saved,
        saved_message="AI 助手配置已保存；API Key 不会明文回显。",
    )


def _save(form: Any) -> RedirectResponse:
    save_ai_assistant_config(_config_from_form(form))
    return RedirectResponse("/system/ai/?saved=1", status_code=303)


@rt("/")
async def index(req: Request) -> Any:
    return guarded_index(req, _render)


@rt("/save", methods=["POST"])
async def save(req: Request) -> Any:
    return await guarded_save(req, _render, _save)


@rt("/test", methods=["POST"])
async def test(req: Request) -> Any:
    denied = require_admin(req)
    if denied is not None:
        return denied
    form = await req.form()
    try:
        result = test_ai_connection(_config_from_form(form))
    except Exception as exc:
        return Div(f"配置无效：{exc}", cls="text-sm text-red-600")
    return connectivity_result_view(result)


__all__ = ["system_ai_app"]
