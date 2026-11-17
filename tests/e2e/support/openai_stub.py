"""Local OpenAI-compatible Chat Completions stub for AI studio E2E tests."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class OpenAIStubState:
    responses: list[dict[str, Any]]
    api_key: str = "sk-e2e-secret-9000"
    delay_seconds: float = 0.0
    requests: list[dict[str, Any]] = field(default_factory=list)
    response_index: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)

    def next_message(self) -> dict[str, Any]:
        with self.lock:
            index = self.response_index
            self.response_index += 1
            if not self.responses:
                return {"role": "assistant", "content": "完成。"}
            return self.responses[min(index, len(self.responses) - 1)]


def _assistant(content: str = "", calls: list[tuple[str, dict[str, Any]]] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [
            {
                "id": f"call_{index}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for index, (name, arguments) in enumerate(calls, 1)
        ]
    return message


class _Handler(BaseHTTPRequestHandler):
    server_version = "OpenAIStub/1.0"

    def do_POST(self) -> None:  # noqa: N802
        state: OpenAIStubState = self.server.state  # type: ignore[attr-defined]
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if self.headers.get("Authorization") != f"Bearer {state.api_key}":
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {"error": {"message": f"invalid key {state.api_key}"}},
            )
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": {"message": "invalid json"}})
            return
        with state.lock:
            state.requests.append(payload)
        if state.delay_seconds:
            time.sleep(state.delay_seconds)
        self._json(HTTPStatus.OK, {"choices": [{"message": state.next_message()}]})

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class OpenAIStub:
    """Scripted loopback server; each request consumes one scripted message."""

    def __init__(
        self,
        responses: list[dict[str, Any]],
        *,
        api_key: str = "sk-e2e-secret-9000",
        delay_seconds: float = 0.0,
    ) -> None:
        self.state = OpenAIStubState(
            responses=responses,
            api_key=api_key,
            delay_seconds=delay_seconds,
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.state = self.state  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    @property
    def api_key(self) -> str:
        return self.state.api_key

    @property
    def request_count(self) -> int:
        with self.state.lock:
            return len(self.state.requests)

    def __enter__(self) -> OpenAIStub:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


__all__ = ["OpenAIStub", "_assistant"]
