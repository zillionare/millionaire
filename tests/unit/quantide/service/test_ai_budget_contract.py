"""Malformed or refused model tool calls consume the host-enforced budget."""

from __future__ import annotations

import httpx
import pytest

from quantide.service import ai_agent
from quantide.service.ai_assistant import AIAssistantConfig
from quantide.service.ai_studio_store import (
    create_session,
    ensure_ai_studio_tables,
    get_session,
    list_messages,
)


def _call(name, arguments):
    return {"id": name, "type": "function", "function": {"name": name, "arguments": arguments}}


@pytest.mark.timeout(5)
@pytest.mark.parametrize("kind,expected_requests", [("unknown", 4), ("malformed", 4), ("mixed", 2)])
def test_refused_tool_calls_exhaust_budget_without_extra_model_turn(db, kind, expected_requests):
    ensure_ai_studio_tables()
    session_id = create_session("bounded refusals")["session_id"]
    requests = 0

    def handler(request):
        nonlocal requests
        requests += 1
        # Bound this test even if the production loop regresses to infinite calls.
        if requests > 4:
            message = {"role": "assistant", "content": "fixture emergency stop"}
        else:
            unknown = _call("no_such_whitelisted_tool", "{}")
            malformed = _call("inspect_market_schema", "{invalid-json")
            calls = (
                [unknown, malformed]
                if kind == "mixed"
                else [unknown if kind == "unknown" else malformed]
            )
            message = {"role": "assistant", "content": "", "tool_calls": calls}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    config = AIAssistantConfig(
        provider_preset="custom",
        base_url="http://127.0.0.1:9/v1",
        model="mock-budget-model",
        api_key="test-budget-key",
        max_tool_steps=4,
    )
    ai_agent.register_transport(session_id, httpx.MockTransport(handler))
    try:
        result = ai_agent.run_agent_round(session_id, "keep calling tools", config)
    finally:
        ai_agent._TRANSPORTS.pop(session_id, None)
    assert result["status"] == "failed"
    assert requests == expected_requests
    assert get_session(session_id)["status"] == "failed"
    assert len([message for message in list_messages(session_id) if message["role"] == "tool"]) == 4


def test_http_timeout_is_not_the_total_tool_workflow_budget(db, monkeypatch):
    """Quick model requests may surround tools taking more than an HTTP timeout."""
    from types import SimpleNamespace

    ensure_ai_studio_tables()
    session_id = create_session("separate request and workflow budgets")["session_id"]
    now = [1000.0]
    monkeypatch.setattr(ai_agent, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def execute(name, arguments, cancel):
        now[0] += 20.0
        return {"ok": True}

    monkeypatch.setattr(ai_agent, "_execute", execute)
    requests = 0

    def handler(request):
        nonlocal requests
        requests += 1
        message = {"role": "assistant", "content": "completed"}
        if requests <= 2:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [_call("inspect_market_schema", "{}")],
            }
        return httpx.Response(200, json={"choices": [{"message": message}]})

    config = AIAssistantConfig(
        provider_preset="custom",
        base_url="http://127.0.0.1:9/v1",
        model="mock-budget-model",
        api_key="test-budget-key",
        timeout_seconds=5,
        max_tool_steps=4,
    )
    ai_agent.register_transport(session_id, httpx.MockTransport(handler))
    try:
        result = ai_agent.run_agent_round(session_id, "inspect two times", config)
    finally:
        ai_agent._TRANSPORTS.pop(session_id, None)
    assert result["status"] == "completed"
    assert requests == 3
    assert now[0] == 1040.0


def test_workflow_clock_budget_still_blocks_another_model_request(db, monkeypatch):
    from types import SimpleNamespace

    ensure_ai_studio_tables()
    session_id = create_session("bounded workflow clock")["session_id"]
    now = [1000.0]
    monkeypatch.setattr(ai_agent, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def execute(name, arguments, cancel):
        now[0] += 301.0
        return {"ok": True}

    monkeypatch.setattr(ai_agent, "_execute", execute)
    requests = 0

    def handler(request):
        nonlocal requests
        requests += 1
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [_call("inspect_market_schema", "{}")],
        }
        return httpx.Response(200, json={"choices": [{"message": message}]})

    config = AIAssistantConfig(
        provider_preset="custom",
        base_url="http://127.0.0.1:9/v1",
        model="mock-budget-model",
        api_key="test-budget-key",
        timeout_seconds=600,
        max_tool_steps=4,
    )
    ai_agent.register_transport(session_id, httpx.MockTransport(handler))
    try:
        result = ai_agent.run_agent_round(session_id, "keep inspecting", config)
    finally:
        ai_agent._TRANSPORTS.pop(session_id, None)
    assert result["status"] == "failed"
    assert requests == 1
