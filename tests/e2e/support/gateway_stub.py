"""Scriptable local qmt-gateway stub used by end-to-end tests."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import threading
import time
import urllib.parse
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _normalize_prefix(prefix: str) -> str:
    text = str(prefix or "/").strip() or "/"
    if not text.startswith("/"):
        text = f"/{text}"
    if text != "/":
        text = text.rstrip("/")
    return text


def _prefix_path(prefix: str, path: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    if prefix == "/":
        return path
    return f"{prefix}{path}"


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_quote(symbol: str = "000001.SZ", price: float = 10.0) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timestamp": _now_text(),
        "1m": {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1000,
            "amount": price * 1000,
        },
    }


@dataclass
class GatewayScenario:
    """Mutable script for the local gateway stub.

    Tests may seed assets, positions, historical orders/trades and quote frames. Submitted
    orders are recorded in memory and, by default, immediately filled with a matching
    trade so adapter queries can exercise a full buy/sell/order/trade/cancel loop.
    """

    asset: dict[str, Any] = field(
        default_factory=lambda: {
            "principal": 100_000,
            "total": 100_000,
            "cash": 100_000,
            "market_value": 0,
            "frozen_cash": 0,
        }
    )
    positions: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    quotes: list[dict[str, Any]] = field(default_factory=lambda: [_default_quote()])
    auto_fill: bool = True
    reject_next_orders: list[str] = field(default_factory=list)
    quote_interval: float = 0.0

    def copy_response_asset(self) -> dict[str, Any]:
        return dict(self.asset)

    def copy_response_positions(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.positions]

    def copy_response_orders(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = [dict(item) for item in self.orders]
        if status:
            rows = [item for item in rows if str(item.get("status") or "") == status]
        return rows

    def copy_response_trades(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.trades]


@dataclass
class GatewayStubState:
    prefix: str
    scenario: GatewayScenario
    lock: threading.RLock = field(default_factory=threading.RLock)

    def submit_order(self, side: str, form: Mapping[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.scenario.reject_next_orders:
                return {
                    "success": False,
                    "error": self.scenario.reject_next_orders.pop(0),
                }
            qtoid = str(form.get("qtoid") or uuid.uuid4())
            symbol = str(form.get("symbol") or "")
            shares = int(float(form.get("shares") or 0))
            price = float(form.get("price") or 0)
            status = "filled" if self.scenario.auto_fill else "submitted"
            order = {
                "qtoid": qtoid,
                "symbol": symbol,
                "side": side,
                "shares": shares,
                "price": price,
                "status": status,
                "filled": shares if self.scenario.auto_fill else 0,
                "strategy_id": str(form.get("strategy_id") or ""),
                "time": _now_text(),
            }
            self.scenario.orders.append(order)
            if self.scenario.auto_fill:
                self.scenario.trades.append(
                    {
                        "tid": f"T{len(self.scenario.trades) + 1}",
                        "qtoid": qtoid,
                        "symbol": symbol,
                        "side": side,
                        "shares": shares,
                        "price": price,
                        "amount": shares * price,
                        "time": order["time"],
                    }
                )
            return {"success": True, "qtoid": qtoid, "order_id": qtoid}

    def cancel_order(self, qtoid: str) -> dict[str, Any]:
        with self.lock:
            for order in self.scenario.orders:
                if str(order.get("qtoid") or "") == qtoid:
                    order["status"] = "cancelled"
                    return {"success": True, "qtoid": qtoid}
        return {"success": False, "error": f"unknown order: {qtoid}"}


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _read_form(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length).decode("utf-8") if length else ""
    values = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {key: value[-1] if value else "" for key, value in values.items()}


def _websocket_accept(key: str) -> str:
    digest = hashlib.sha1(f"{key}{_WEBSOCKET_GUID}".encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _ws_text_frame(payload: Mapping[str, Any]) -> bytes:
    body = _json_bytes(payload)
    size = len(body)
    if size <= 125:
        header = bytes([0x81, size])
    elif size <= 65535:
        header = bytes([0x81, 126]) + size.to_bytes(2, "big")
    else:
        header = bytes([0x81, 127]) + size.to_bytes(8, "big")
    return header + body


def _build_gateway_handler(state: GatewayStubState) -> type[BaseHTTPRequestHandler]:
    class ScriptableGatewayHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == _prefix_path(state.prefix, "/ws/quotes"):
                self._serve_quote_websocket()
                return
            if path == _prefix_path(state.prefix, "/ping"):
                self._send_json({"ok": True})
                return
            if path == _prefix_path(state.prefix, "/api/trade/asset"):
                with state.lock:
                    self._send_json(state.scenario.copy_response_asset())
                return
            if path == _prefix_path(state.prefix, "/api/trade/positions"):
                with state.lock:
                    self._send_json(state.scenario.copy_response_positions())
                return
            if path == _prefix_path(state.prefix, "/api/trade/orders"):
                query = urllib.parse.urlparse(self.path).query
                status = urllib.parse.parse_qs(query).get("status", [None])[-1]
                with state.lock:
                    self._send_json(state.scenario.copy_response_orders(status=status))
                return
            if path == _prefix_path(state.prefix, "/api/trade/trades"):
                with state.lock:
                    self._send_json(state.scenario.copy_response_trades())
                return
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            form = _read_form(self)
            if path == _prefix_path(state.prefix, "/auth/login"):
                self._send_json(
                    {"success": True, "username": form.get("username", "")},
                    headers={"Set-Cookie": "gateway_stub_session=ok; Path=/"},
                )
                return
            if path == _prefix_path(state.prefix, "/api/trade/buy"):
                self._send_json(state.submit_order("buy", form))
                return
            if path == _prefix_path(state.prefix, "/api/trade/sell"):
                self._send_json(state.submit_order("sell", form))
                return
            if path == _prefix_path(state.prefix, "/api/trade/cancel"):
                self._send_json(state.cancel_order(str(form.get("qtoid") or "")))
                return
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def _serve_quote_websocket(self) -> None:
            key = self.headers.get("Sec-WebSocket-Key", "")
            if not key:
                self._send_json(
                    {"error": "missing websocket key"}, status=HTTPStatus.BAD_REQUEST
                )
                return
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {_websocket_accept(key)}\r\n\r\n"
            )
            self.connection.sendall(response.encode("ascii"))
            with state.lock:
                quotes = [dict(item) for item in state.scenario.quotes]
                interval = state.scenario.quote_interval
            for quote in quotes:
                self.connection.sendall(_ws_text_frame(quote))
                if interval > 0:
                    time.sleep(interval)
            self.connection.sendall(b"\x88\x00")
            self.close_connection = True

        def _send_json(
            self,
            payload: Any,
            status: HTTPStatus = HTTPStatus.OK,
            headers: Mapping[str, str] | None = None,
        ) -> None:
            body = _json_bytes(payload)
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ScriptableGatewayHandler


@dataclass
class GatewayStub:
    """Running gateway stub server instance."""

    host: str
    port: int
    prefix: str
    scenario: GatewayScenario
    _server: ThreadingHTTPServer
    _thread: threading.Thread

    @property
    def base_url(self) -> str:
        return (
            f"http://{self.host}:{self.port}{'' if self.prefix == '/' else self.prefix}"
        )

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}{_prefix_path(self.prefix, '/ws/quotes')}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


def start_gateway_stub(
    host: str = "127.0.0.1",
    prefix: str = "/",
    scenario: GatewayScenario | Mapping[str, Any] | None = None,
) -> GatewayStub:
    """Start a local gateway stub with auth, trade, query, cancel and quote paths."""
    normalized_prefix = _normalize_prefix(prefix)
    if scenario is None:
        scenario_obj = GatewayScenario()
    elif isinstance(scenario, GatewayScenario):
        scenario_obj = scenario
    else:
        scenario_obj = GatewayScenario(**dict(scenario))
    state = GatewayStubState(prefix=normalized_prefix, scenario=scenario_obj)
    server = ThreadingHTTPServer((host, 0), _build_gateway_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return GatewayStub(
        host=host,
        port=int(server.server_address[1]),
        prefix=normalized_prefix,
        scenario=scenario_obj,
        _server=server,
        _thread=thread,
    )


@contextmanager
def running_gateway_stub(
    host: str = "127.0.0.1",
    prefix: str = "/",
    scenario: GatewayScenario | Mapping[str, Any] | None = None,
) -> Iterator[GatewayStub]:
    """Yield a running scriptable gateway stub and stop it automatically."""
    stub = start_gateway_stub(host=host, prefix=prefix, scenario=scenario)
    try:
        yield stub
    finally:
        stub.stop()
