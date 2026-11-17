"""Bounded OpenAI-compatible tool-calling agent for the Web factor studio."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from quantide.config.settings import get_factor_dir
from quantide.service.ai_assistant import (
    AIAssistantConfig,
    load_ai_assistant_config,
    redact_secrets,
)
from quantide.service.ai_factor_tools import (
    TOOL_HANDLERS,
    TOOL_SCHEMAS,
    AIToolError,
    execute_tool,
)
from quantide.service.ai_studio_store import (
    append_message,
    get_session,
    list_messages,
    update_session,
)

SYSTEM_PROMPT = """你是 Millionaire 的 A 股因子研究助手。你必须遵守：
1. 只通过提供的白名单工具工作，绝不要求或模拟 Shell、任意路径文件读写。
2. 新因子必须先用 write_factor_plugin 写入 factor_dir，再调用 run_factor_wind_tunnel。
3. 风洞返回 FAIL 或 INCONCLUSIVE 时，读取 diagnostics/first_difference 修正代码并重检；
   禁止修改风洞阈值、禁止跳过失败项。
4. 只有当前指纹风洞 PASS 后，才可调用 run_factor_ic_study 或保存预设。
5. 因子计算必须按 asset 分组（例如 .over("asset")），禁止 shift(-n)、reverse、
   全样本未来均值/排名等未来函数。
6. 用简洁中文向不会编程的用户解释进度和结论，不夸大 IC 与收益。
"""

_ACTIVE: dict[str, threading.Event] = {}
_ACTIVE_LOCK = threading.RLock()


class AIClientError(RuntimeError):
    """Credential-safe model call failure."""

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AIChatClient:
    """Small synchronous Chat Completions client with structured tools."""

    def __init__(
        self,
        config: AIAssistantConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    def _url(self) -> str:
        base = self.config.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        try:
            with httpx.Client(
                timeout=float(self.config.timeout_seconds),
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = client.post(self._url(), headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise AIClientError("timeout", "模型请求超时。") from exc
        except httpx.RequestError as exc:
            message = redact_secrets(str(exc), self.config.api_key)
            raise AIClientError("unreachable", f"模型端点不可达：{message}") from exc
        if response.status_code >= 400:
            message = _safe_http_error(response, self.config.api_key)
            code = "auth_failed" if response.status_code in {401, 403} else "http_error"
            if response.status_code == 429:
                code = "rate_limited"
            raise AIClientError(code, message, response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise AIClientError("incompatible", "模型响应不是合法 JSON。") from exc
        if not isinstance(body, dict):
            raise AIClientError("incompatible", "模型响应 JSON 不是对象。")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AIClientError("incompatible", "模型响应缺少 choices。")
        assistant_message = choices[0].get("message")
        if not isinstance(assistant_message, dict):
            raise AIClientError("incompatible", "模型响应缺少 message。")
        return assistant_message


def _safe_http_error(response: httpx.Response, api_key: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    detail: str = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
        elif error:
            detail = str(error)
    text = detail or f"HTTP {response.status_code}"
    return redact_secrets(text, api_key)


def _history(session_id: str) -> list[dict[str, str]]:
    messages = []
    for row in list_messages(session_id):
        if row.get("role") not in {"user", "assistant"}:
            continue
        content = str(row.get("content") or "").strip()
        if content:
            messages.append({"role": row["role"], "content": content})
    return messages[-12:]


def _card(stage: str, status: str, title: str, **extra: Any) -> dict[str, Any]:
    return {"stage": stage, "status": status, "title": title, **extra}


def _tool_call_parts(call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    function = call.get("function") if isinstance(call, dict) else None
    if not isinstance(function, dict):
        return "", "", {}
    name = str(function.get("name") or "")
    call_id = str(call.get("id") or "")
    raw = function.get("arguments") or "{}"
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError):
        arguments = {}
    return name, call_id, arguments if isinstance(arguments, dict) else {}


def _execute(name: str, arguments: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
    return execute_tool(name, arguments, cancel=cancel)


def _finish(
    session_id: str,
    status: str,
    content: str,
    cards: list[dict[str, Any]],
    *,
    factor_id: str = "",
) -> dict[str, Any]:
    update_session(
        session_id,
        status=status,
        active_factor_id=factor_id or None,
    )
    append_message(session_id, "assistant", content, step_cards=cards)
    return {"status": status, "content": content, "cards": cards}


def _safe_failure(session_id: str, cards: list[dict[str, Any]], message: str) -> dict[str, Any]:
    cards = [*cards, _card("error", "failed", "本轮停止", message=message)]
    update_session(session_id, status="failed")
    append_message(session_id, "assistant", message, step_cards=cards)
    return {"status": "failed", "content": message, "cards": cards}


def _generate_card(result: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    return _card(
        "generate",
        "done" if result.get("ok") else "failed",
        "生成因子代码",
        factor_id=arguments.get("factor_id") or result.get("factor_id"),
        code=arguments.get("code") or "",
        source_hash=result.get("source_hash"),
    )


def _wind_card(result: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    return _card(
        "wind_tunnel",
        "passed" if result.get("status") == "PASS" else "failed",
        "风洞体检",
        factor_id=arguments.get("factor_id"),
        status_text=result.get("status"),
        first_difference=result.get("first_difference"),
        diagnostics=result.get("diagnostics") or [],
        orthogonality=result.get("orthogonality") or {},
    )


def _study_card(result: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    return _card(
        "study",
        "done" if result.get("ok") else "failed",
        "IC 与十分位结论",
        factor_id=arguments.get("factor_id") or result.get("factor_id"),
        results=result.get("results") or [],
        common_cohort=result.get("common_cohort"),
        data_cutoff=result.get("data_cutoff"),
        message=result.get("message"),
    )


def _preset_card(result: dict[str, Any], _arguments: dict[str, Any]) -> dict[str, Any]:
    return _card(
        "preset",
        "done" if result.get("ok") else "failed",
        "保存预设与消融回测",
        preset=result.get("preset"),
        ablation=result.get("ablation"),
        message=result.get("message") or result.get("ablation_error"),
    )


_TOOL_CARD_BUILDERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "write_factor_plugin": _generate_card,
    "run_factor_wind_tunnel": _wind_card,
    "run_factor_ic_study": _study_card,
    "save_preset_and_run_ablation": _preset_card,
}


def _tool_card(name: str, result: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    builder = _TOOL_CARD_BUILDERS.get(name)
    if builder is not None:
        return builder(result, arguments)
    return _card(name, "done" if result.get("ok") else "failed", name, result=result)


def _record_tool(
    session_id: str,
    cards: list[dict[str, Any]],
    name: str,
    result: dict[str, Any],
) -> None:
    append_message(
        session_id,
        "tool",
        json.dumps(result, ensure_ascii=False, default=str)[:12000],
        step_cards=cards[-1:],
    )


@dataclass
class _RoundState:
    session_id: str
    config: AIAssistantConfig
    cancel: threading.Event
    messages: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    active_factor_id: str = ""
    used_steps: int = 0
    repair_rounds: int = 0
    ic_done: bool = False


def _finish_state(state: _RoundState, status: str, content: str) -> dict[str, Any]:
    return _finish(state.session_id, status, content, state.cards, factor_id=state.active_factor_id)


def _fail_state(state: _RoundState, message: str) -> dict[str, Any]:
    return _safe_failure(state.session_id, state.cards, message)


def _auto_study(state: _RoundState, factor_id: str) -> None:
    result = _execute(
        "run_factor_ic_study", {"factor_id": factor_id, "lookback": "1y"}, state.cancel
    )
    state.used_steps += 1
    state.ic_done = True
    state.cards.append(_tool_card("run_factor_ic_study", result, {"factor_id": factor_id}))
    _record_tool(state.session_id, state.cards, "run_factor_ic_study", result)


def _wind_followup(
    state: _RoundState, result: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, Any] | None:
    if result.get("status") == "PASS":
        if not state.ic_done and state.used_steps < state.config.max_tool_steps:
            _auto_study(state, state.active_factor_id or str(arguments.get("factor_id") or ""))
        return None
    state.repair_rounds += 1
    state.cards.append(
        _card(
            "repair",
            "running" if state.repair_rounds < state.config.max_repair_rounds else "failed",
            f"自动修复第 {state.repair_rounds} 轮",
            first_difference=result.get("first_difference"),
        )
    )
    if state.repair_rounds >= state.config.max_repair_rounds:
        return _fail_state(
            state,
            f"风洞连续 {state.config.max_repair_rounds} 轮未通过，已停止自动修复。"
            "请查看首次差异与诊断后调整需求，或手动编辑因子。",
        )
    return None


def _run_tool_call(state: _RoundState, call: dict[str, Any]) -> dict[str, Any] | None:
    if state.used_steps >= state.config.max_tool_steps:
        return _fail_state(
            state,
            f"已达到单轮最多 {state.config.max_tool_steps} 个工具步数，受控停止。",
        )
    if state.cancel.is_set():
        return _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
    name, call_id, arguments = _tool_call_parts(call)
    if name not in TOOL_HANDLERS:
        result = {"ok": False, "code": "unknown_tool", "message": f"未知工具: {name}"}
    else:
        result = _execute(name, arguments, state.cancel)
        state.used_steps += 1
    if name == "write_factor_plugin" and result.get("ok"):
        state.active_factor_id = str(result.get("factor_id") or "")
        update_session(state.session_id, active_factor_id=state.active_factor_id)
    state.cards.append(_tool_card(name, result, arguments))
    _record_tool(state.session_id, state.cards, name, result)
    append_message(state.session_id, "assistant", "", step_cards=state.cards)
    if name == "run_factor_wind_tunnel":
        terminal = _wind_followup(state, result, arguments)
        if terminal is not None:
            return terminal
    state.messages.append(
        {
            "role": "tool",
            "tool_call_id": call_id,
            "name": name,
            "content": json.dumps(result, ensure_ascii=False, default=str)[:12000],
        }
    )
    return None


def _handle_calls(state: _RoundState, tool_calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    for call in tool_calls:
        result = _run_tool_call(state, call)
        if result is not None:
            return result
    return None


def _run_loop(
    session_id: str,
    user_text: str,
    config: AIAssistantConfig,
    cancel: threading.Event,
) -> dict[str, Any]:
    history = _history(session_id)
    if history and history[-1].get("role") == "user" and history[-1].get("content") == user_text:
        history = history[:-1]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + f"\n当前 factor_dir：{get_factor_dir()}"},
        *history,
        {"role": "user", "content": user_text},
    ]
    transport = _TRANSPORTS.get(session_id)
    client = AIChatClient(config, transport=transport)
    state = _RoundState(
        session_id=session_id,
        config=config,
        cancel=cancel,
        messages=messages,
        cards=[_card("understand", "done", "理解需求", request=user_text)],
    )
    while state.used_steps < config.max_tool_steps:
        if cancel.is_set():
            return _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
        try:
            message = client.chat(state.messages)
        except AIClientError as exc:
            return _fail_state(state, f"模型调用失败：{exc}")
        content = str(message.get("content") or "").strip()
        tool_calls = message.get("tool_calls") or []
        state.messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        if not isinstance(tool_calls, list) or not tool_calls:
            return _finish_state(state, "completed", content or "本轮没有新的工具动作，已结束。")
        terminal = _handle_calls(state, tool_calls)
        if terminal is not None:
            return terminal
    return _fail_state(state, f"已达到单轮最多 {config.max_tool_steps} 个工具步数，受控停止。")


def run_agent_round(
    session_id: str,
    user_text: str,
    config: AIAssistantConfig | None = None,
    *,
    cancel: threading.Event | None = None,
) -> dict[str, Any]:
    """Run one synchronous bounded agent round; useful to workers and tests."""
    if get_session(session_id) is None:
        raise KeyError(f"AI 会话不存在: {session_id}")
    text = str(user_text or "").strip()
    if not text:
        raise ValueError("用户需求不能为空")
    resolved = config or load_ai_assistant_config()
    if resolved is None:
        raise ValueError("尚未配置 AI 助手")
    event = cancel or threading.Event()
    update_session(session_id, status="running")
    append_message(session_id, "user", text)
    try:
        return _run_loop(session_id, text, resolved, event)
    except AIToolError as exc:
        return _safe_failure(session_id, [], f"工具调用失败：{exc.message}")
    except Exception as exc:
        logger.exception("AI 工坊轮次失败")
        return _safe_failure(session_id, [], f"本轮异常停止：{type(exc).__name__}")


def start_agent_round(
    session_id: str,
    user_text: str,
    config: AIAssistantConfig | None = None,
) -> threading.Event:
    """Start one background agent round and return its cancellation event."""
    if get_session(session_id) is None:
        raise KeyError(f"AI 会话不存在: {session_id}")
    event = threading.Event()
    with _ACTIVE_LOCK:
        previous = _ACTIVE.get(session_id)
        if previous is not None:
            previous.set()
        _ACTIVE[session_id] = event

    def _target() -> None:
        try:
            run_agent_round(session_id, user_text, config, cancel=event)
        finally:
            with _ACTIVE_LOCK:
                if _ACTIVE.get(session_id) is event:
                    _ACTIVE.pop(session_id, None)

    threading.Thread(target=_target, name=f"ai-studio-{session_id}", daemon=True).start()
    return event


def cancel_session(session_id: str) -> bool:
    """Cancel the active model request and any child wind-tunnel/study process."""
    with _ACTIVE_LOCK:
        event = _ACTIVE.get(session_id)
    if event is None:
        if get_session(session_id) is not None:
            update_session(session_id, status="cancelled")
        return False
    event.set()
    update_session(session_id, status="cancelling")
    return True


def is_session_running(session_id: str) -> bool:
    with _ACTIVE_LOCK:
        event = _ACTIVE.get(session_id)
    return event is not None and not event.is_set()


_TRANSPORTS: dict[str, httpx.BaseTransport] = {}


def register_transport(session_id: str, transport: httpx.BaseTransport) -> None:
    """Test hook: route future model calls for a session through a mock transport."""
    _TRANSPORTS[session_id] = transport


__all__ = [
    "AIChatClient",
    "AIClientError",
    "SYSTEM_PROMPT",
    "cancel_session",
    "is_session_running",
    "register_transport",
    "run_agent_round",
    "start_agent_round",
]
