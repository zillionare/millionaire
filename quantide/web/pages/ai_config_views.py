"""Reusable AI assistant settings fields for wizard and system pages."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Button as ActionButton
from fasthtml.common import (
    Div,
    Input,
    Label,
    NotStr,
    Option,
    P,
    Select,
    Span,
)

from quantide.service.ai_assistant import (
    PROVIDER_CHOICES,
    PROVIDER_PRESETS,
    AIAssistantPublicView,
    public_view,
)

AI_FORM_FIELDS = {
    "provider": "provider_preset",
    "base_url": "base_url",
    "model": "model",
    "api_key": "api_key",
    "timeout": "timeout_seconds",
    "repair_rounds": "max_repair_rounds",
    "tool_steps": "max_tool_steps",
}

_PRESET_JS = """
(function (select) {
  var presets = %s;
  var option = select.options[select.selectedIndex];
  var preset = presets[option.value];
  if (!preset) return;
  var form = select.closest('form') || document;
  var base = form.querySelector('[name="base_url"]');
  var model = form.querySelector('[name="model"]');
  if (base && !base.value) base.value = preset.base_url;
  if (model && !model.value) model.value = preset.model;
})(this);
"""


def _field(label: str, child: Any, hint: str = "") -> Div:
    return Div(
        Label(label, cls="q-label"),
        child,
        P(hint, cls="text-xs text-gray-500 mt-1") if hint else None,
        cls="mb-3",
    )


def ai_provider_select(view: AIAssistantPublicView) -> Select:
    return Select(
        *[
            Option(
                f"{PROVIDER_PRESETS[preset]['label']}",
                value=preset,
                selected=view.provider_preset == preset,
            )
            for preset in PROVIDER_CHOICES
        ],
        name=AI_FORM_FIELDS["provider"],
        cls="q-input",
        onchange=NotStr(_PRESET_JS % _preset_js_payload()),
    )


def _preset_js_payload() -> str:
    import json

    return json.dumps(
        {
            key: {"base_url": value["base_url"], "model": value["model"]}
            for key, value in PROVIDER_PRESETS.items()
        },
        ensure_ascii=False,
    )


def ai_config_fields(
    view: AIAssistantPublicView | None = None,
    *,
    compact: bool = False,
) -> Div:
    """Build credential-safe fields; blank key means keep the saved key."""
    resolved = view or public_view()
    key_hint = "留空表示保持已保存的密钥，不会回显明文。"
    if resolved.api_key_masked:
        key_hint = f"已保存：{resolved.api_key_masked}。留空表示保持不变。"
    return Div(
        _field("服务商预设", ai_provider_select(resolved)),
        _field(
            "Base URL",
            Input(name=AI_FORM_FIELDS["base_url"], value=resolved.base_url, cls="q-input"),
        ),
        _field(
            "模型",
            Input(name=AI_FORM_FIELDS["model"], value=resolved.model, cls="q-input"),
        ),
        _field(
            "API Key",
            Input(
                name=AI_FORM_FIELDS["api_key"],
                type="password",
                value="",
                placeholder=resolved.api_key_masked or "本地 Ollama 可留空",
                autocomplete="new-password",
                cls="q-input",
            ),
            key_hint,
        ),
        Div(
            _field(
                "超时（秒）",
                Input(
                    name=AI_FORM_FIELDS["timeout"],
                    type="number",
                    min="1",
                    max="600",
                    value=str(resolved.timeout_seconds),
                    cls="q-input",
                ),
            ),
            _field(
                "最多自动修复轮次",
                Input(
                    name=AI_FORM_FIELDS["repair_rounds"],
                    type="number",
                    min="1",
                    max="10",
                    value=str(resolved.max_repair_rounds),
                    cls="q-input",
                ),
            ),
            _field(
                "单轮最多工具步数",
                Input(
                    name=AI_FORM_FIELDS["tool_steps"],
                    type="number",
                    min="1",
                    max="64",
                    value=str(resolved.max_tool_steps),
                    cls="q-input",
                ),
            ),
            cls="grid grid-cols-1 md:grid-cols-3 gap-3",
        ),
        cls="" if compact else "space-y-1",
    )


def ai_config_card(
    *,
    action: str = "/system/ai/save",
    test_action: str | None = "/system/ai/test",
    view: AIAssistantPublicView | None = None,
    optional: bool = False,
) -> Div:
    resolved = view or public_view()
    return Div(
        Div(
            Span("AI 助手配置", cls="text-base font-semibold text-gray-900"),
            Span(
                "OPTIONAL · 可跳过" if optional else "系统维护",
                cls="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600",
            ),
            cls="flex items-center",
        ),
        P(
            "用于「AI 写因子」工坊。API Key 仅保存在本机配置目录（权限 0600），"
            "页面、接口与日志只显示掩码。",
            cls="mt-1 mb-3 text-sm text-gray-500",
        ),
        ai_config_fields(resolved),
        Div(
            ActionButton("保存配置", type="submit", cls="q-btn q-btn--primary"),
            ActionButton(
                "测试连接",
                type="button",
                cls="q-btn ml-2",
                hx_post=test_action,
                hx_include="closest form",
                hx_target="#ai-connection-result",
                hx_swap="innerHTML",
            )
            if test_action
            else None,
            Span(id="ai-connection-result", cls="ml-3 text-sm"),
            cls="mt-3 flex items-center",
        ),
        cls="rounded-xl border border-gray-200 bg-white p-4 shadow-sm",
    )


__all__ = ["AI_FORM_FIELDS", "ai_config_card", "ai_config_fields", "ai_provider_select"]


def ai_wizard_card() -> Div:
    """Render the optional in-wizard AI card without leaving the current step."""
    view = public_view()
    return Div(
        Div(
            Span("AI 助手配置（可选）", cls="text-base font-semibold text-gray-900"),
            Span("OPTIONAL · 可跳过", cls="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs"),
            cls="flex items-center",
        ),
        P(
            "这一步可以跳过；不配置 AI 不会影响数据、因子、回测和仿真功能。"
            "保存后仍可在「系统维护 → AI 助手」随时重配。",
            cls="mt-1 mb-3 text-sm text-gray-500",
        ),
        ai_config_fields(view),
        Div(
            ActionButton(
                "保存 AI 配置",
                type="button",
                cls="q-btn q-btn--primary",
                hx_post="/init-wizard/ai/save",
                hx_include="closest form",
                hx_target="#ai-wizard-result",
                hx_swap="innerHTML",
            ),
            ActionButton(
                "测试连接",
                type="button",
                cls="q-btn ml-2",
                hx_post="/init-wizard/ai/test",
                hx_include="closest form",
                hx_target="#ai-wizard-result",
                hx_swap="innerHTML",
            ),
            Span("你也可以直接点击下一步跳过。", cls="ml-3 text-xs text-gray-500"),
            cls="mt-3 flex flex-wrap items-center",
        ),
        Div(id="ai-wizard-result", cls="mt-2"),
        cls="mt-5 rounded-xl border border-gray-200 bg-gray-50 p-4",
    )


def connectivity_result_view(result: Any) -> Div:
    """Render one probe result with a safe tone and stable code."""
    tone = "text-green-700" if result.ok else "text-red-600"
    icon = "✅" if result.ok else "❌"
    return Div(
        f"{icon} {result.message}（{result.code}）",
        cls=f"text-sm {tone}",
    )
