"""Bounded tool-calling repair loop for the Web AI factor studio."""

from __future__ import annotations

import json
import threading
from typing import Any

import httpx
import pytest

from quantide.service import ai_agent
from quantide.service.ai_assistant import AIAssistantConfig
from quantide.service.ai_studio_store import (
    create_session,
    ensure_ai_studio_tables,
    get_session,
    latest_assistant_cards,
)
from quantide.service.ai_agent import register_transport, run_agent_round


def _tool_response(calls: list[tuple[str, dict[str, Any]]], content: str = "") -> httpx.Response:
    tool_calls = [
        {
            "id": f"call_{index}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }
        for index, (name, arguments) in enumerate(calls, 1)
    ]
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    }
                }
            ]
        },
    )


def _config(repair_rounds: int = 3) -> AIAssistantConfig:
    return AIAssistantConfig(
        provider_preset="custom",
        base_url="http://127.0.0.1:9/v1",
        model="mock-model",
        api_key="sk-agent-secret-1234",
        max_repair_rounds=repair_rounds,
        max_tool_steps=12,
    )


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[list[dict[str, Any]]] = []
        self.writes: list[str] = []
        self.wind_calls = 0
        self.ic_calls = 0

    def execute(self, name: str, arguments: dict[str, Any], *, cancel=None) -> dict[str, Any]:
        if name == "write_factor_plugin":
            self.writes.append(str(arguments.get("code") or ""))
            return {
                "ok": True,
                "factor_id": arguments.get("factor_id"),
                "source_hash": f"hash{len(self.writes)}",
            }
        if name == "run_factor_wind_tunnel":
            self.wind_calls += 1
            if self.wind_calls == 1:
                return {
                    "ok": False,
                    "status": "FAIL",
                    "factor_id": arguments.get("factor_id"),
                    "first_difference": {
                        "date": "2024-01-03",
                        "asset": "000001.SZ",
                        "expected": 0.0,
                        "actual": 1.5,
                    },
                    "diagnostics": [
                        {
                            "code": "cross_section_isolation",
                            "message": "missing .over('asset')",
                            "first_difference": {"asset": "000001.SZ"},
                        }
                    ],
                    "orthogonality": {"max_abs_rank_corr": 0.3},
                }
            return {
                "ok": True,
                "status": "PASS",
                "factor_id": arguments.get("factor_id"),
                "first_difference": None,
                "diagnostics": [],
                "orthogonality": {
                    "max_abs_rank_corr": 0.25,
                    "nearest_peer_id": "bias_5",
                    "high_collinearity": False,
                },
            }
        if name == "run_factor_ic_study":
            self.ic_calls += 1
            return {
                "ok": True,
                "factor_id": arguments.get("factor_id"),
                "data_cutoff": "2024-12-31",
                "results": [
                    {
                        "holding_days": 5,
                        "rank_ic": {"mean": 0.031, "icir": 0.42, "n_days": 100},
                        "deciles": {"d1_minus_d10": -0.12},
                        "as_of_date": "2024-12-31",
                    }
                ],
            }
        return {"ok": True}


def test_agent_repairs_bad_factor_after_first_difference(db, monkeypatch) -> None:
    ensure_ai_studio_tables()
    session = create_session("修复闭环")
    recorder = _Recorder()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        recorder.requests.append(json.loads(request.content)["messages"])
        if calls == 1:
            return _tool_response([("write_factor_plugin", {"factor_id": "ai_momentum", "code": "bad"})])
        if calls == 2:
            return _tool_response([("run_factor_wind_tunnel", {"factor_id": "ai_momentum"})])
        if calls == 3:
            return _tool_response(
                [("write_factor_plugin", {"factor_id": "ai_momentum", "code": "fixed .over('asset')"})]
            )
        if calls == 4:
            return _tool_response([("run_factor_wind_tunnel", {"factor_id": "ai_momentum"})])
        return _tool_response([], "因子已通过风洞并完成检验。")

    monkeypatch.setattr(ai_agent, "execute_tool", recorder.execute)
    register_transport(session["session_id"], httpx.MockTransport(handler))
    try:
        result = run_agent_round(session["session_id"], "写一个动量因子", _config())
    finally:
        ai_agent._TRANSPORTS.pop(session["session_id"], None)

    assert result["status"] == "completed"
    assert recorder.writes == ["bad", "fixed .over('asset')"]
    assert recorder.wind_calls == 2
    assert recorder.ic_calls == 1
    assert calls == 5
    assert any(
        "first_difference" in json.dumps(message, ensure_ascii=False)
        for message in recorder.requests[2]
    )
    stages = {card["stage"] for card in latest_assistant_cards(session["session_id"])}
    assert {"understand", "generate", "wind_tunnel", "repair", "study"} <= stages
    stored = get_session(session["session_id"])
    assert stored is not None and stored["active_factor_id"] == "ai_momentum"


def test_agent_stops_after_max_repair_rounds(db, monkeypatch) -> None:
    ensure_ai_studio_tables()
    session = create_session("修复上限")
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        messages = json.loads(request.content)["messages"]
        recorder.requests.append(messages)
        last = messages[-1] if messages else {}
        if last.get("role") == "tool" and last.get("name") == "run_factor_wind_tunnel":
            return _tool_response(
                [("write_factor_plugin", {"factor_id": "ai_momentum", "code": "still bad"})]
            )
        if last.get("role") == "tool" and last.get("name") == "write_factor_plugin":
            return _tool_response([("run_factor_wind_tunnel", {"factor_id": "ai_momentum"})])
        return _tool_response([("write_factor_plugin", {"factor_id": "ai_momentum", "code": "bad"})])

    def always_fail(name: str, arguments: dict[str, Any], *, cancel=None) -> dict[str, Any]:
        if name == "run_factor_wind_tunnel":
            recorder.wind_calls += 1
            return {
                "ok": False,
                "status": "FAIL",
                "factor_id": arguments.get("factor_id"),
                "first_difference": {"date": "2024-01-03", "asset": "000001.SZ"},
                "diagnostics": [],
            }
        if name == "write_factor_plugin":
            recorder.writes.append("bad")
            return {"ok": True, "factor_id": arguments.get("factor_id"), "source_hash": "x"}
        return {"ok": True}

    monkeypatch.setattr(ai_agent, "execute_tool", always_fail)
    register_transport(session["session_id"], httpx.MockTransport(handler))
    try:
        result = run_agent_round(
            session["session_id"], "写一个坏因子", _config(repair_rounds=3)
        )
    finally:
        ai_agent._TRANSPORTS.pop(session["session_id"], None)

    assert result["status"] == "failed"
    assert recorder.wind_calls == 3
    assert "连续 3 轮未通过" in result["content"]
    stored = get_session(session["session_id"])
    assert stored is not None and stored["status"] == "failed"


def test_agent_cancel_stops_next_step(db, monkeypatch) -> None:
    ensure_ai_studio_tables()
    session = create_session("取消")
    event = threading.Event()

    def handler(_request: httpx.Request) -> httpx.Response:
        return _tool_response([("write_factor_plugin", {"factor_id": "ai_momentum", "code": "draft"})])

    def execute(name: str, arguments: dict[str, Any], *, cancel=None) -> dict[str, Any]:
        event.set()
        return {"ok": True, "factor_id": arguments.get("factor_id"), "source_hash": "x"}

    monkeypatch.setattr(ai_agent, "execute_tool", execute)
    register_transport(session["session_id"], httpx.MockTransport(handler))
    try:
        result = run_agent_round(session["session_id"], "写因子", _config(), cancel=event)
    finally:
        ai_agent._TRANSPORTS.pop(session["session_id"], None)

    assert result["status"] == "cancelled"
    stored = get_session(session["session_id"])
    assert stored is not None and stored["status"] == "cancelled"


def test_model_error_message_never_contains_api_key(db) -> None:
    ensure_ai_studio_tables()
    session = create_session("鉴权失败")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad sk-agent-secret-1234"}})

    register_transport(session["session_id"], httpx.MockTransport(handler))
    try:
        result = run_agent_round(session["session_id"], "写因子", _config())
    finally:
        ai_agent._TRANSPORTS.pop(session["session_id"], None)

    assert result["status"] == "failed"
    assert "sk-agent-secret-1234" not in result["content"]
    assert "sk-****1234" in result["content"]
