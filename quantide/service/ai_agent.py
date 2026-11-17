"""Bounded OpenAI-compatible tool-calling agent for the Web factor studio."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

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

# Checked before each model request; in-flight calls retain their own hard budgets.
_ROUND_BUDGET_SECONDS = 300.0

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
_GENERATION: dict[str, object] = {}
_RUNNING: dict[str, object] = {}
_CANCELLED: dict[str, object] = {}
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

    def chat(
        self, messages: list[dict[str, Any]], cancel: threading.Event | None = None
    ) -> dict[str, Any]:
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
            response = self._post(headers, payload, cancel)
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

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=float(self.config.timeout_seconds),
            trust_env=False,
            transport=self.transport,
        )

    def _post(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
        cancel: threading.Event | None,
    ) -> httpx.Response:
        """POST with a cancellable async socket when a stop event is supplied."""
        if cancel is None:
            with self._http_client() as client:
                return client.post(self._url(), headers=headers, json=payload)
        results: queue.Queue[tuple[str, Any]] = queue.Queue()
        holder: dict[str, Any] = {}

        async def _request() -> httpx.Response:
            holder["loop"] = asyncio.get_running_loop()
            holder["task"] = asyncio.current_task()
            async with httpx.AsyncClient(
                timeout=float(self.config.timeout_seconds),
                trust_env=False,
                transport=cast(Any, self.transport),
            ) as client:
                return await client.post(self._url(), headers=headers, json=payload)

        def _run() -> None:
            try:
                results.put(("ok", asyncio.run(_request())))
            except BaseException as exc:  # cross-thread transport failure
                results.put(("error", exc))

        worker = threading.Thread(target=_run, daemon=True, name="ai-model-request")
        worker.start()
        return _await_request(worker, results, holder, cancel)


def _cancel_async_request(holder: dict[str, Any]) -> bool:
    loop = holder.get("loop")
    task = holder.get("task")
    if loop is None or task is None:
        return False
    try:
        loop.call_soon_threadsafe(task.cancel)
    except RuntimeError:
        return False
    return True


def _read_request_event(
    worker: threading.Thread, results: queue.Queue[tuple[str, Any]]
) -> tuple[str, Any] | None:
    try:
        return results.get(timeout=0.05)
    except queue.Empty:
        if not worker.is_alive():
            raise AIClientError("incompatible", "模型请求线程异常结束。") from None
        return None


def _await_request(
    worker: threading.Thread,
    results: queue.Queue[tuple[str, Any]],
    holder: dict[str, Any],
    cancel: threading.Event,
) -> httpx.Response:
    while True:
        if cancel.is_set():
            # The worker may not have published its loop/task yet. Re-issue the
            # thread-safe cancellation until the request holder is ready.
            _cancel_async_request(holder)
            if not worker.is_alive():
                worker.join(timeout=2)
                raise AIClientError("cancelled", "模型请求已取消。")
        event = _read_request_event(worker, results)
        if event is None:
            continue
        if cancel.is_set():
            worker.join(timeout=2)
            raise AIClientError("cancelled", "模型请求已取消。")
        kind, value = event
        if kind == "error":
            raise value
        return cast(httpx.Response, value)


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


def _tool_call_parts(call: dict[str, Any]) -> tuple[str, str, dict[str, Any], str]:
    function = call.get("function") if isinstance(call, dict) else None
    if not isinstance(function, dict):
        return "", "", {}, "missing function"
    name = str(function.get("name") or "")
    call_id = str(call.get("id") or "")
    raw = function.get("arguments") or "{}"
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return name, call_id, {}, "arguments must be a JSON object"
    if not isinstance(arguments, dict):
        return name, call_id, {}, "arguments must be a JSON object"
    return name, call_id, arguments, ""


def _execute(name: str, arguments: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
    return execute_tool(name, arguments, cancel=cancel)


def _round_is_current(session_id: str, token: object | None) -> bool:
    if token is None:
        return True
    with _ACTIVE_LOCK:
        return _GENERATION.get(session_id) is token


def _cancellation_committed(session_id: str, token: object | None) -> bool:
    return token is not None and _CANCELLED.get(session_id) is token


def _cancellation_pending(session_id: str, token: object | None) -> bool:
    if _cancellation_committed(session_id, token):
        return True
    event = _ACTIVE.get(session_id)
    return event is not None and event.is_set() and _GENERATION.get(session_id) is token


def _commit_if_current(session_id: str, token: object | None, commit: Callable[[], Any]) -> bool:
    """Atomically check generation ownership and persist non-terminal side effects."""
    with _ACTIVE_LOCK:
        if not _round_is_current(session_id, token):
            return False
        if _cancellation_pending(session_id, token):
            return False
        commit()
    return True


def _commit_terminal(
    session_id: str,
    token: object | None,
    status: str,
    content: str,
    cards: list[dict[str, Any]],
    *,
    factor_id: str = "",
    failure_card: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Commit one legal terminal state under the generation/cancel contract."""
    with _ACTIVE_LOCK:
        if not _round_is_current(session_id, token):
            return None
        if _cancellation_pending(session_id, token):
            status = "cancelled"
            content = "已停止本轮 AI 工作。"
            cards = []
        elif failure_card is not None:
            cards = [*cards, failure_card]
        update_session(session_id, status=status, active_factor_id=factor_id or None)
        append_message(session_id, "assistant", content, step_cards=cards)
    return {"status": status, "content": content, "cards": cards}


def _blocked_result(state: _RoundState) -> dict[str, Any]:
    with _ACTIVE_LOCK:
        cancelled = _cancellation_pending(state.session_id, state.round_token)
    if cancelled:
        return _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
    return _superseded_result()


def _finish(
    session_id: str,
    status: str,
    content: str,
    cards: list[dict[str, Any]],
    *,
    factor_id: str = "",
    token: object | None = None,
) -> dict[str, Any]:
    result = _commit_terminal(
        session_id,
        token,
        status,
        content,
        cards,
        factor_id=factor_id,
    )
    if result is None:
        return {"status": "superseded", "content": "", "cards": []}
    return result


def _safe_failure(
    session_id: str,
    cards: list[dict[str, Any]],
    message: str,
    *,
    token: object | None = None,
) -> dict[str, Any]:
    result = _commit_terminal(
        session_id,
        token,
        "failed",
        message,
        cards,
        failure_card=_card("error", "failed", "本轮停止", message=message),
    )
    if result is None:
        return {"status": "superseded", "content": "", "cards": []}
    return result


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
        universe_filter=result.get("universe_filter"),
        universe=result.get("universe"),
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
    token: object | None = None,
) -> None:
    _commit_if_current(
        session_id,
        token,
        lambda: append_message(
            session_id,
            "tool",
            json.dumps(result, ensure_ascii=False, default=str)[:12000],
            step_cards=cards[-1:],
        ),
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
    model_rounds: int = 0
    deadline: float = 0.0
    round_token: object | None = None
    ic_done: bool = False


def _finish_state(state: _RoundState, status: str, content: str) -> dict[str, Any]:
    return _finish(
        state.session_id,
        status,
        content,
        state.cards,
        factor_id=state.active_factor_id,
        token=state.round_token,
    )


def _fail_state(state: _RoundState, message: str) -> dict[str, Any]:
    return _safe_failure(state.session_id, state.cards, message, token=state.round_token)


def _auto_study(state: _RoundState, factor_id: str) -> None:
    result = _execute(
        "run_factor_ic_study", {"factor_id": factor_id, "lookback": "1y"}, state.cancel
    )
    if not _round_is_current(state.session_id, state.round_token):
        return
    state.used_steps += 1
    state.ic_done = True
    state.cards.append(_tool_card("run_factor_ic_study", result, {"factor_id": factor_id}))
    _record_tool(
        state.session_id,
        state.cards,
        "run_factor_ic_study",
        result,
        state.round_token,
    )


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


def _superseded_result() -> dict[str, Any]:
    return {"status": "superseded", "content": "", "cards": []}


def _tool_result(
    state: _RoundState,
    name: str,
    arguments: dict[str, Any],
    argument_error: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if argument_error:
        return {"ok": False, "code": "invalid_arguments", "message": argument_error}, None
    if name not in TOOL_HANDLERS:
        return {"ok": False, "code": "unknown_tool", "message": f"未知工具: {name}"}, None
    result = _execute(name, arguments, state.cancel)
    if not _round_is_current(state.session_id, state.round_token):
        return None, _superseded_result()
    if state.cancel.is_set():
        return None, _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
    return result, None


def _run_tool_call(state: _RoundState, call: dict[str, Any]) -> dict[str, Any] | None:
    if not _round_is_current(state.session_id, state.round_token):
        return _superseded_result()
    if state.used_steps >= state.config.max_tool_steps:
        return _fail_state(
            state,
            f"已达到单轮最多 {state.config.max_tool_steps} 个工具步数，受控停止。",
        )
    if state.cancel.is_set():
        return _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
    name, call_id, arguments, argument_error = _tool_call_parts(call)
    state.used_steps += 1
    result, terminal = _tool_result(state, name, arguments, argument_error)
    if terminal is not None:
        return terminal
    assert result is not None
    if name == "write_factor_plugin" and result.get("ok"):
        state.active_factor_id = str(result.get("factor_id") or "")
        committed = _commit_if_current(
            state.session_id,
            state.round_token,
            lambda: update_session(state.session_id, active_factor_id=state.active_factor_id),
        )
        if not committed:
            return _blocked_result(state)
    state.cards.append(_tool_card(name, result, arguments))
    _record_tool(state.session_id, state.cards, name, result, state.round_token)
    committed = _commit_if_current(
        state.session_id,
        state.round_token,
        lambda: append_message(state.session_id, "assistant", "", step_cards=state.cards),
    )
    if not committed:
        return _blocked_result(state)
    state.messages.append(
        {
            "role": "tool",
            "tool_call_id": call_id,
            "name": name,
            "content": json.dumps(result, ensure_ascii=False, default=str)[:12000],
        }
    )
    if name == "run_factor_wind_tunnel":
        return _wind_followup(state, result, arguments)
    return None


def _handle_calls(state: _RoundState, tool_calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    for call in tool_calls:
        result = _run_tool_call(state, call)
        if result is not None:
            return result
    return None


def _model_turn(
    state: _RoundState,
    client: AIChatClient,
    cancel: threading.Event,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if cancel.is_set():
        return None, _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
    model_limit = max(1, int(state.config.max_tool_steps))
    if state.model_rounds >= model_limit or time.monotonic() >= state.deadline:
        return None, _fail_state(state, "模型轮次或时间预算已耗尽，受控停止。")
    state.model_rounds += 1
    try:
        message = client.chat(state.messages, cancel=cancel)
    except AIClientError as exc:
        if exc.code == "cancelled" or cancel.is_set():
            return None, _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
        return None, _fail_state(state, f"模型调用失败：{exc}")
    if cancel.is_set():
        return None, _finish_state(state, "cancelled", "已停止本轮 AI 工作。")
    return message, None


def _round_messages(session_id: str, user_text: str) -> list[dict[str, Any]]:
    history = _history(session_id)
    if history and history[-1].get("role") == "user" and history[-1].get("content") == user_text:
        history = history[:-1]
    return [
        {"role": "system", "content": SYSTEM_PROMPT + f"\n当前 factor_dir：{get_factor_dir()}"},
        *history,
        {"role": "user", "content": user_text},
    ]


def _run_loop(
    session_id: str,
    user_text: str,
    config: AIAssistantConfig,
    cancel: threading.Event,
    generation: object | None = None,
) -> dict[str, Any]:
    transport = _TRANSPORTS.get(session_id)
    client = AIChatClient(config, transport=transport)
    state = _RoundState(
        session_id=session_id,
        config=config,
        cancel=cancel,
        messages=_round_messages(session_id, user_text),
        cards=[_card("understand", "done", "理解需求", request=user_text)],
        deadline=time.monotonic() + _ROUND_BUDGET_SECONDS,
        round_token=generation or cancel,
    )
    while state.used_steps < config.max_tool_steps:
        message, terminal = _model_turn(state, client, cancel)
        if terminal is not None:
            return terminal
        if message is None:
            return _fail_state(state, "模型返回空响应，已受控停止。")
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
    _generation: object | None = None,
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
    generation = _generation
    if generation is None:
        generation = object()
        with _ACTIVE_LOCK:
            _GENERATION[session_id] = generation

    def _start() -> None:
        _RUNNING[session_id] = generation
        update_session(session_id, status="running")
        append_message(session_id, "user", text)

    started = _commit_if_current(session_id, generation, _start)
    if not started:
        return _superseded_result()
    try:
        return _run_loop(session_id, text, resolved, event, generation)
    except AIToolError as exc:
        return _safe_failure(session_id, [], f"工具调用失败：{exc.message}", token=generation)
    except Exception as exc:
        logger.exception("AI 工坊轮次失败")
        return _safe_failure(
            session_id, [], f"本轮异常停止：{type(exc).__name__}", token=generation
        )


def start_agent_round(
    session_id: str,
    user_text: str,
    config: AIAssistantConfig | None = None,
) -> threading.Event:
    """Start one background agent round and return its cancellation event."""
    if get_session(session_id) is None:
        raise KeyError(f"AI 会话不存在: {session_id}")
    event = threading.Event()
    generation = object()
    with _ACTIVE_LOCK:
        previous = _ACTIVE.get(session_id)
        if previous is not None:
            previous.set()
        _ACTIVE[session_id] = event
        _GENERATION[session_id] = generation

    def _target() -> None:
        try:
            run_agent_round(session_id, user_text, config, cancel=event, _generation=generation)
        finally:
            with _ACTIVE_LOCK:
                if _ACTIVE.get(session_id) is event:
                    _ACTIVE.pop(session_id, None)

    threading.Thread(target=_target, name=f"ai-studio-{session_id}", daemon=True).start()
    return event


def cancel_session(session_id: str) -> bool:
    """Cancel the active model request and any child wind-tunnel/study process."""
    with _ACTIVE_LOCK:
        session = get_session(session_id)
        status = str((session or {}).get("status") or "")
        generation = _GENERATION.get(session_id)
        event = _ACTIVE.get(session_id)
        if event is None:
            if status in {"running", "cancelling"}:
                update_session(session_id, status="cancelled")
            return False
        if _RUNNING.get(session_id) is generation and status in {
            "completed",
            "failed",
            "cancelled",
        }:
            return False
        event.set()
        if generation is not None:
            _CANCELLED[session_id] = generation
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
