"""Bounded tool-calling repair loop for the Web AI factor studio."""

from __future__ import annotations

import json
import threading
from typing import Any

import httpx
import pytest

from quantide.service import ai_agent
from quantide.service.ai_agent import register_transport, run_agent_round
from quantide.service.ai_assistant import AIAssistantConfig
from quantide.service.ai_studio_store import (
    create_session,
    ensure_ai_studio_tables,
    get_session,
    latest_assistant_cards,
)


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
            return _tool_response(
                [("write_factor_plugin", {"factor_id": "ai_momentum", "code": "bad"})]
            )
        if calls == 2:
            return _tool_response([("run_factor_wind_tunnel", {"factor_id": "ai_momentum"})])
        if calls == 3:
            return _tool_response(
                [
                    (
                        "write_factor_plugin",
                        {"factor_id": "ai_momentum", "code": "fixed .over('asset')"},
                    )
                ]
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
        return _tool_response(
            [("write_factor_plugin", {"factor_id": "ai_momentum", "code": "bad"})]
        )

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
        result = run_agent_round(session["session_id"], "写一个坏因子", _config(repair_rounds=3))
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
        return _tool_response(
            [("write_factor_plugin", {"factor_id": "ai_momentum", "code": "draft"})]
        )

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


def _run_slow_http_cancel(mode: str) -> None:
    import select
    import socket
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    started = threading.Event()
    closed = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            started.set()
            if mode == "body":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "100")
                self.end_headers()
                self.wfile.write(b'{"choices":')
                self.wfile.flush()
            while True:
                ready, _, _ = select.select([self.connection], [], [], 0.05)
                if ready:
                    try:
                        data = self.connection.recv(1, socket.MSG_PEEK)
                    except OSError:
                        data = b""
                    if data == b"":
                        closed.set()
                        return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cancel = threading.Event()
    result: list[str] = []
    config = AIAssistantConfig(
        provider_preset="custom",
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        model="offline",
        timeout_seconds=6,
    )
    client = ai_agent.AIChatClient(config)

    def call() -> None:
        try:
            client.chat([{"role": "user", "content": "test"}], cancel=cancel)
        except ai_agent.AIClientError as exc:
            result.append(exc.code)

    worker = threading.Thread(target=call)
    worker.start()
    try:
        assert started.wait(3)
        began = time.monotonic()
        cancel.set()
        worker.join(2)
        elapsed = time.monotonic() - began
        assert result == ["cancelled"]
        assert not worker.is_alive()
        assert elapsed < 1.5
        assert closed.wait(1)
        assert not [item for item in threading.enumerate() if item.name == "ai-model-request"]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("mode", ["headers", "body"])
def test_real_slow_http_cancel_reclaims_request_thread(mode: str) -> None:
    _run_slow_http_cancel(mode)


def test_cancel_before_request_holder_is_ready_is_retried() -> None:
    import asyncio
    import queue
    import time

    results: queue.Queue[tuple[str, Any]] = queue.Queue()
    holder: dict[str, Any] = {}
    cancel = threading.Event()

    def run_request() -> None:
        time.sleep(0.2)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        holder["loop"] = loop

        async def wait_forever() -> None:
            await asyncio.sleep(2)

        task = loop.create_task(wait_forever())
        holder["task"] = task
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            results.put(("error", asyncio.CancelledError()))
        finally:
            loop.close()

    worker = threading.Thread(target=run_request, daemon=True)
    worker.start()
    cancel.set()
    started = time.monotonic()
    with pytest.raises(ai_agent.AIClientError) as exc:
        ai_agent._await_request(worker, results, holder, cancel)

    assert exc.value.code == "cancelled"
    assert time.monotonic() - started < 1.5
    assert not worker.is_alive()


def test_superseded_round_cannot_overwrite_new_completed_state(db, monkeypatch) -> None:
    import time

    ensure_ai_studio_tables()
    session = create_session("round identity")
    session_id = session["session_id"]
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _tool_response([("run_factor_wind_tunnel", {"factor_id": "owned_factor"})])
        return _tool_response([], "NEW COMPLETED")

    def execute(name: str, _arguments: dict[str, Any], *, cancel=None) -> dict[str, Any]:
        if name == "run_factor_wind_tunnel":
            return {"ok": True, "status": "PASS"}
        if name == "run_factor_ic_study":
            started.set()
            assert release.wait(5)
            return {"ok": True, "results": []}
        raise AssertionError(name)

    monkeypatch.setattr(ai_agent, "execute_tool", execute)
    register_transport(session_id, httpx.MockTransport(handler))
    try:
        ai_agent.start_agent_round(session_id, "old", _config())
        assert started.wait(3)
        ai_agent.start_agent_round(session_id, "new", _config())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if (get_session(session_id) or {}).get("status") == "completed":
                break
            time.sleep(0.01)
        assert (get_session(session_id) or {}).get("status") == "completed"
        release.set()
        time.sleep(0.3)

        assert (get_session(session_id) or {}).get("status") == "completed"
        assert (get_session(session_id) or {}).get("active_factor_id") is None
        cards = latest_assistant_cards(session_id)
        assert cards and cards[-1].get("status") != "running"
    finally:
        release.set()
        ai_agent._TRANSPORTS.pop(session_id, None)


def test_superseded_round_cannot_persist_late_start(db, monkeypatch) -> None:
    ensure_ai_studio_tables()
    session_id = create_session("late start")["session_id"]
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    real_run = ai_agent.run_agent_round

    def delayed(session_id, user_text, *args, **kwargs):
        if user_text == "old":
            started.set()
            assert release.wait(5)
        try:
            return real_run(session_id, user_text, *args, **kwargs)
        finally:
            if user_text == "old":
                finished.set()

    def handler(_request: httpx.Request) -> httpx.Response:
        return _tool_response([], "NEW COMPLETED")

    monkeypatch.setattr(ai_agent, "execute_tool", lambda *args, **kwargs: {"ok": True})
    register_transport(session_id, httpx.MockTransport(handler))
    try:
        with monkeypatch.context() as patch:
            patch.setattr(ai_agent, "run_agent_round", delayed)
            ai_agent.start_agent_round(session_id, "old", _config())
            assert started.wait(3)
            ai_agent.start_agent_round(session_id, "new", _config())
            deadline = __import__("time").monotonic() + 3
            while __import__("time").monotonic() < deadline:
                if (get_session(session_id) or {}).get("status") == "completed":
                    break
                __import__("time").sleep(0.01)
            release.set()
            assert finished.wait(2)

        stored = get_session(session_id) or {}
        assert stored.get("status") == "completed"
        assert stored.get("active_factor_id") is None
        cards = latest_assistant_cards(session_id)
        assert cards
        assert {card.get("stage") for card in cards} == {"understand"}
    finally:
        release.set()
        ai_agent._TRANSPORTS.pop(session_id, None)


def test_cancel_without_active_round_preserves_completed_result(db) -> None:
    from quantide.service.ai_studio_store import update_session

    session_id = create_session("completed stop")["session_id"]
    update_session(session_id, status="completed")
    assert ai_agent.cancel_session(session_id) is False
    assert get_session(session_id)["status"] == "completed"


def test_cancel_commit_cannot_overwrite_new_generation(db, monkeypatch) -> None:
    from quantide.service.ai_studio_store import update_session

    session_id = create_session("cancel generation race")["session_id"]
    old_event, new_event = threading.Event(), threading.Event()
    old_generation, new_generation = object(), object()
    entered, release = threading.Event(), threading.Event()
    attempted, committed = threading.Event(), threading.Event()
    real_update = ai_agent.update_session
    with ai_agent._ACTIVE_LOCK:
        ai_agent._ACTIVE[session_id] = old_event
        ai_agent._GENERATION[session_id] = old_generation
    update_session(session_id, status="running")

    def delayed_update(target, **values):
        if (
            threading.current_thread().name == "owned-cancel"
            and values.get("status") == "cancelling"
        ):
            entered.set()
            assert release.wait(3)
        return real_update(target, **values)

    def complete_new():
        attempted.set()
        with ai_agent._ACTIVE_LOCK:
            ai_agent._ACTIVE[session_id] = new_event
            ai_agent._GENERATION[session_id] = new_generation
        ai_agent._finish(session_id, "completed", "NEW", [], token=new_generation)
        committed.set()

    monkeypatch.setattr(ai_agent, "update_session", delayed_update)
    old_thread = threading.Thread(
        target=ai_agent.cancel_session, args=(session_id,), name="owned-cancel"
    )
    new_thread = threading.Thread(target=complete_new, name="owned-new")
    try:
        old_thread.start()
        assert entered.wait(2)
        new_thread.start()
        assert attempted.wait(2)
        committed.wait(0.2)
        release.set()
        old_thread.join(2)
        new_thread.join(2)
        assert not old_thread.is_alive() and not new_thread.is_alive()
        assert committed.is_set()
        assert get_session(session_id)["status"] == "completed"
    finally:
        release.set()
        old_thread.join(2)
        if new_thread.ident is not None:
            new_thread.join(2)
        with ai_agent._ACTIVE_LOCK:
            ai_agent._ACTIVE.pop(session_id, None)
            ai_agent._GENERATION.pop(session_id, None)
