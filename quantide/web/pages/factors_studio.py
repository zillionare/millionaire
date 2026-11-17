"""Web AI factor studio with staged progress cards and safe actions."""

from __future__ import annotations

from typing import Any

from fasthtml.common import (
    H1,
    H2,
    A,
    Details,
    Div,
    Form,
    Input,
    P,
    Pre,
    Span,
    Summary,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
)
from fasthtml.common import Button as ActionButton
from starlette.requests import Request
from starlette.responses import RedirectResponse

from quantide.service.ai_agent import (
    cancel_session,
    is_session_running,
    start_agent_round,
)
from quantide.service.ai_assistant import (
    config_from_form,
    load_ai_assistant_config,
    public_view,
    save_ai_assistant_config,
    test_ai_connection,
)
from quantide.service.ai_factor_tools import execute_tool
from quantide.service.ai_studio_store import (
    append_message,
    create_session,
    get_session,
    latest_assistant_cards,
    list_messages,
    list_sessions,
)
from quantide.service.factor_tracking import save_profile, trigger_refresh
from quantide.web.application import fast_app
from quantide.web.layouts.main import MainLayout
from quantide.web.pages.ai_config_views import ai_config_fields, connectivity_result_view
from quantide.web.pages.factors import _factor_menu
from quantide.web.theme import AppTheme

factors_studio_app, rt = fast_app(hdrs=AppTheme.headers())


def _layout(title: str, active: str = "/factors/studio") -> MainLayout:
    layout = MainLayout(title=title)
    layout.content_max_width = "max-w-[1600px]"
    layout.header_active = "因子"
    layout.sidebar_menu = _factor_menu(active)
    layout.set_sidebar_active(active)
    return layout


def _configured() -> bool:
    config = load_ai_assistant_config()
    return config is not None and bool(config.api_key or config.provider_preset == "ollama")


def _number(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _percent(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value) * 100:+.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def _config_panel(error: str = "") -> Any:
    view = public_view()
    return Div(
        H1("AI 写因子", cls="text-2xl font-bold text-gray-900"),
        P(
            "用自然语言描述因子想法，AI 会写代码、自动过风洞并在失败时修复。"
            "首次使用请先配置 OpenAI 兼容模型。",
            cls="mt-1 text-sm text-gray-500",
        ),
        Div(error, cls="mt-3 text-sm text-red-600") if error else None,
        Form(
            ai_config_fields(view),
            ActionButton("保存并开始", type="submit", cls="q-btn q-btn--primary mt-3"),
            ActionButton(
                "测试连接",
                type="button",
                cls="q-btn ml-2 mt-3",
                hx_post="/factors/studio/config/test",
                hx_include="closest form",
                hx_target="#studio-config-result",
                hx_swap="innerHTML",
            ),
            Span(id="studio-config-result", cls="ml-3 text-sm"),
            action="/factors/studio/config",
            method="post",
            cls="mt-5 rounded-xl border border-gray-200 bg-white p-5 shadow-sm",
        ),
        cls="max-w-2xl mx-auto py-8",
    )


def _session_sidebar(active_id: str) -> Any:
    sessions = list_sessions()
    rows = [
        A(
            Div(str(item.get("title") or "未命名会话"), cls="text-sm font-medium truncate"),
            Div(
                f"{item.get('status') or 'idle'} · {str(item.get('updated_at') or '')[:16]}",
                cls="text-xs text-gray-500",
            ),
            href=f"/factors/studio/?session_id={item['session_id']}",
            cls=(
                "block rounded-lg border px-3 py-2 "
                + (
                    "border-[#e41815] bg-red-50"
                    if item["session_id"] == active_id
                    else "border-gray-100 hover:bg-gray-50"
                )
            ),
        )
        for item in sessions
    ]
    return Div(
        H2("会话", cls="text-sm font-semibold text-gray-700"),
        Form(
            ActionButton("＋ 新建会话", type="submit", cls="q-btn q-btn--primary w-full"),
            action="/factors/studio/sessions",
            method="post",
            cls="my-3",
        ),
        Div(*rows, cls="space-y-2") if rows else P("暂无会话。", cls="text-sm text-gray-500"),
        A("管理 AI 助手配置", href="/system/ai", cls="mt-4 block text-xs text-[#e41815]"),
        cls="w-72 flex-shrink-0 rounded-xl border border-gray-100 bg-white p-4 shadow-sm",
    )


def _status_badge(item: dict[str, Any]) -> Span:
    status = str(item.get("status_text") or item.get("status") or "")
    tone = {
        "PASS": "bg-green-50 text-green-700",
        "passed": "bg-green-50 text-green-700",
        "FAIL": "bg-red-50 text-red-700",
        "failed": "bg-red-50 text-red-700",
        "done": "bg-blue-50 text-blue-700",
        "running": "bg-amber-50 text-amber-700",
    }.get(status, "bg-gray-100 text-gray-600")
    return Span(status or "—", cls=f"rounded-full px-2 py-0.5 text-xs {tone}")


def _difference(item: dict[str, Any]) -> Any:
    difference = item.get("first_difference")
    if not isinstance(difference, dict):
        return None
    return P(
        f"首次差异：{difference.get('date') or difference.get('time') or '—'} · "
        f"{difference.get('asset') or '—'} · 期望 {difference.get('expected')} / "
        f"实际 {difference.get('actual')}",
        cls="mt-1 text-xs text-red-700",
    )


def _code_block(item: dict[str, Any]) -> Any:
    code = str(item.get("code") or "")
    if not code:
        return None
    return Details(
        Summary("查看生成代码（默认折叠）", cls="cursor-pointer text-xs font-medium text-gray-600"),
        Pre(
            code,
            cls="mt-2 max-h-80 overflow-auto rounded-lg bg-gray-950 p-3 text-xs text-gray-100",
        ),
        cls="mt-2",
    )


def _ic_table(item: dict[str, Any]) -> Any:
    rows = item.get("results") or []
    if not rows:
        return None
    body = []
    for row in rows:
        rank = row.get("rank_ic") or {}
        deciles = row.get("deciles") or {}
        body.append(
            Tr(
                Td(str(row.get("holding_days") or "—")),
                Td(_number(rank.get("mean"), 4)),
                Td(_number(rank.get("icir"), 3)),
                Td(_percent(deciles.get("d1_minus_d10"))),
                Td(str(row.get("as_of_date") or "—")),
            )
        )
    return Table(
        Thead(Tr(Th("持有期"), Th("RankIC"), Th("ICIR"), Th("D1-D10"), Th("截至"))),
        Tbody(*body),
        cls="mt-2 w-full text-left text-xs",
    )


def _orthogonality(item: dict[str, Any]) -> Any:
    ortho = item.get("orthogonality") or {}
    if not ortho:
        return None
    peer = ortho.get("nearest_peer_id") or "—"
    corr = _number(ortho.get("max_abs_rank_corr"), 3)
    warning = " · 高共线性" if ortho.get("high_collinearity") else ""
    return P(f"最高相关现有因子：{peer} · |ρ| {corr}{warning}", cls="mt-1 text-xs text-gray-600")


def _card_actions(item: dict[str, Any], session_id: str, factor_id: str) -> Any:
    if not factor_id or item.get("stage") != "wind_tunnel" or item.get("status") != "passed":
        return None
    return Div(
        Form(
            ActionButton("开启每日自动跟踪", type="submit", cls="q-btn"),
            action=f"/factors/studio/sessions/{session_id}/actions/track",
            method="post",
            cls="inline",
        ),
        Form(
            ActionButton("加入策略预设做消融回测", type="submit", cls="q-btn q-btn--primary ml-2"),
            action=f"/factors/studio/sessions/{session_id}/actions/preset",
            method="post",
            cls="inline",
        ),
        A("查看因子详情页 →", href=f"/factors/{factor_id}", cls="ml-3 text-sm text-[#e41815]"),
        cls="mt-3 flex flex-wrap items-center gap-2",
    )


def _card(item: dict[str, Any], session_id: str, factor_id: str) -> Any:
    stage = str(item.get("stage") or "")
    title = str(item.get("title") or stage)
    children: list[Any] = [
        Div(
            Span(title, cls="font-medium text-gray-900"),
            Span(_status_badge(item), cls="ml-2"),
            cls="flex items-center",
        )
    ]
    if stage == "understand":
        children.append(P(str(item.get("request") or ""), cls="mt-1 text-sm text-gray-600"))
    if stage == "generate":
        children.append(_code_block(item))
    if stage in {"wind_tunnel", "repair"}:
        children.append(_difference(item))
        children.append(_orthogonality(item))
        for diagnostic in item.get("diagnostics") or []:
            children.append(
                P(
                    f"{diagnostic.get('code')}: {diagnostic.get('message')}",
                    cls="mt-1 text-xs text-gray-600",
                )
            )
    if stage == "study":
        children.append(_ic_table(item))
        children.append(_orthogonality(item))
    if stage == "preset":
        preset = item.get("preset") or {}
        if preset:
            children.append(
                P(
                    f"预设：{preset.get('preset_id')} · {len(preset.get('features') or [])} 个因子",
                    cls="mt-1 text-xs text-gray-600",
                )
            )
    children.append(_card_actions(item, session_id, factor_id))
    return Div(*children, cls="rounded-xl border border-gray-100 bg-white p-4 shadow-sm")


def _message_bubble(message: dict[str, Any]) -> Any:
    role = message.get("role")
    content = str(message.get("content") or "").strip()
    if not content:
        return None
    if role == "user":
        return Div(
            Div("你", cls="text-xs text-gray-500 mb-1"),
            Div(content, cls="rounded-xl bg-[#e41815] px-4 py-3 text-sm text-white"),
            cls="ml-auto max-w-3xl",
        )
    if role == "assistant":
        return Div(
            Div("AI", cls="text-xs text-gray-500 mb-1"),
            Div(content, cls="rounded-xl bg-white px-4 py-3 text-sm text-gray-800 shadow-sm"),
            cls="max-w-3xl",
        )
    return None


def _conversation(session: dict[str, Any]) -> Any:
    session_id = str(session["session_id"])
    factor_id = str(session.get("active_factor_id") or "")
    messages = list_messages(session_id)
    cards = latest_assistant_cards(session_id)
    bubbles = [item for item in (_message_bubble(row) for row in messages) if item is not None]
    running = is_session_running(session_id) or session.get("status") in {"running", "cancelling"}
    return Div(
        Div(
            Div(
                H1(str(session.get("title") or "AI 因子会话"), cls="text-xl font-bold"),
                Span(
                    f"状态：{session.get('status') or 'idle'}"
                    + (f" · 当前因子 {factor_id}" if factor_id else ""),
                    cls="ml-2 text-xs text-gray-500",
                ),
                cls="flex items-baseline",
            ),
            Form(
                ActionButton("停止", type="submit", cls="q-btn"),
                action=f"/factors/studio/sessions/{session_id}/cancel",
                method="post",
                cls="inline",
            )
            if running
            else None,
            cls="flex items-center justify-between",
        ),
        Div(*bubbles, cls="mt-4 space-y-4")
        if bubbles
        else P("输入需求开始。", cls="mt-4 text-sm text-gray-500"),
        Div(
            *[_card(item, session_id, factor_id) for item in cards],
            cls="mt-4 space-y-3",
        )
        if cards
        else None,
        Form(
            Input(
                name="message",
                placeholder="例如：写一个 20 日缩量反转因子，并按证券分组计算",
                autocomplete="off",
                required=True,
                cls="q-input w-full",
            ),
            ActionButton(
                "发送",
                type="submit",
                cls="q-btn q-btn--primary ml-2",
                disabled=running,
            ),
            action=f"/factors/studio/sessions/{session_id}/messages",
            method="post",
            cls="mt-5 flex items-center",
        ),
        id="studio-session-panel",
        hx_get=f"/factors/studio/sessions/{session_id}/panel",
        hx_trigger="every 2s",
        hx_swap="outerHTML",
        cls="flex-1 rounded-xl border border-gray-100 bg-gray-50 p-5",
    )


def _studio_body(req: Request) -> Any:
    if not _configured():
        return _config_panel()
    session_id = str(req.query_params.get("session_id") or "").strip()
    session = get_session(session_id) if session_id else None
    if session is None:
        sessions = list_sessions()
        session = get_session(str(sessions[0]["session_id"])) if sessions else None
    if session is None:
        session = create_session("新的 AI 因子会话")
    return Div(
        _session_sidebar(str(session["session_id"])),
        _conversation(session),
        cls="flex gap-5 items-start",
    )


@rt("/")
def index(req: Request) -> Any:
    layout = _layout("AI 写因子")
    layout.set_main_block(lambda: Div(_studio_body(req), cls="py-6"))
    return layout.render(req)


@rt("/config", methods=["POST"])
async def save_config(req: Request) -> Any:
    form = await req.form()
    values = {
        key: form.get(key)
        for key in (
            "provider_preset",
            "base_url",
            "model",
            "api_key",
            "timeout_seconds",
            "max_repair_rounds",
            "max_tool_steps",
        )
    }
    try:
        save_ai_assistant_config(config_from_form(values, existing=load_ai_assistant_config()))
    except Exception as exc:
        panel = _config_panel(str(exc))
        layout = _layout("AI 写因子")
        layout.set_main_block(lambda: panel)
        return layout.render(req)
    return RedirectResponse("/factors/studio/", status_code=303)


@rt("/config/test", methods=["POST"])
async def test_config(req: Request) -> Any:
    form = await req.form()
    values = {
        key: form.get(key)
        for key in (
            "provider_preset",
            "base_url",
            "model",
            "api_key",
            "timeout_seconds",
            "max_repair_rounds",
            "max_tool_steps",
        )
    }
    try:
        result = test_ai_connection(config_from_form(values, existing=load_ai_assistant_config()))
    except Exception as exc:
        return Div(f"配置无效：{exc}", cls="text-sm text-red-600")
    return connectivity_result_view(result)


@rt("/sessions", methods=["POST"])
async def new_session() -> RedirectResponse:
    session = create_session()
    return RedirectResponse(f"/factors/studio/?session_id={session['session_id']}", status_code=303)


@rt("/sessions/{session_id}/messages", methods=["POST"])
async def post_message(req: Request, session_id: str) -> RedirectResponse:
    form = await req.form()
    text = str(form.get("message") or "").strip()
    if text and _configured() and get_session(session_id) is not None:
        start_agent_round(session_id, text)
    return RedirectResponse(f"/factors/studio/?session_id={session_id}", status_code=303)


@rt("/sessions/{session_id}/panel")
def session_panel(session_id: str) -> Any:
    session = get_session(session_id)
    if session is None:
        return Div("会话不存在。", cls="text-sm text-red-600")
    return _conversation(session)


@rt("/sessions/{session_id}/cancel", methods=["POST"])
async def cancel(session_id: str) -> RedirectResponse:
    cancel_session(session_id)
    return RedirectResponse(f"/factors/studio/?session_id={session_id}", status_code=303)


@rt("/sessions/{session_id}/actions/track", methods=["POST"])
async def action_track(session_id: str) -> RedirectResponse:
    session = get_session(session_id)
    factor_id = str((session or {}).get("active_factor_id") or "")
    if factor_id:
        save_profile(
            factor_id,
            lookback="3y",
            primary_holding_days=5,
            comparison_holding_days=[1, 3, 5],
            price_field="open",
            enabled=True,
        )
        trigger_refresh(factor_id)
        append_message(session_id, "assistant", f"已开启 {factor_id} 的每日自动跟踪。")
    return RedirectResponse(f"/factors/studio/?session_id={session_id}", status_code=303)


@rt("/sessions/{session_id}/actions/preset", methods=["POST"])
async def action_preset(session_id: str) -> RedirectResponse:
    session = get_session(session_id)
    factor_id = str((session or {}).get("active_factor_id") or "")
    if factor_id:
        preset_id = f"ai_{factor_id}"[:64]
        result = execute_tool(
            "save_preset_and_run_ablation",
            {
                "preset_id": preset_id,
                "name": f"AI 因子 {factor_id}",
                "add_factor_id": factor_id,
                "label_kind": "raw_return",
            },
        )
        append_message(
            session_id,
            "assistant",
            "已保存因子预设。",
            step_cards=[
                {
                    "stage": "preset",
                    "status": "done" if result.get("ok") else "failed",
                    "title": "保存预设与消融回测",
                    **result,
                }
            ],
        )
    return RedirectResponse(f"/factors/studio/?session_id={session_id}", status_code=303)


__all__ = ["factors_studio_app"]
