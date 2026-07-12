"""Scriptable local qmt-gateway stub used by end-to-end tests."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import socket
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


def _normalize_side_text(value: str | None) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


@dataclass
class GatewaySubmitScript:
    """Scripted submit-order transition for the local gateway stub."""

    side: str | None = None
    symbol: str | None = None
    response: dict[str, Any] = field(default_factory=dict)
    order: dict[str, Any] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    asset_after: dict[str, Any] | None = None
    positions_after: list[dict[str, Any]] | None = None
    expose_order_qtoid: bool = True
    expose_trade_qtoid: bool = True

    def matches(self, side: str, form: Mapping[str, Any]) -> bool:
        expected_side = _normalize_side_text(self.side)
        if expected_side is not None and expected_side != _normalize_side_text(side):
            return False
        expected_symbol = str(self.symbol or "").strip()
        if expected_symbol and expected_symbol != str(form.get("symbol") or "").strip():
            return False
        return True


@dataclass
class GatewayCancelScript:
    """Scripted cancel-order transition for the local gateway stub."""

    qtoid: str | None = None
    order_id: str | None = None
    response: dict[str, Any] = field(default_factory=dict)
    order_status: str | None = "cancelled"

    def matches(self, qtoid: str, order_id: str | None = None) -> bool:
        if self.qtoid and self.qtoid != qtoid:
            return False
        if self.order_id and self.order_id != str(order_id or ""):
            return False
        return True


@dataclass
class GatewayScenario:
    """Mutable script for the local gateway stub.

    Tests may seed assets, positions, historical orders/trades and quote frames. Submitted
    orders are recorded in memory and may also be driven by explicit submit/cancel
    scripts so paper/live tests can share the same trade facts and query snapshots.
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
    submit_scripts: list[GatewaySubmitScript] = field(default_factory=list)
    cancel_scripts: list[GatewayCancelScript] = field(default_factory=list)
    quote_interval: float = 0.0

    def copy_response_asset(self) -> dict[str, Any]:
        return dict(self.asset)

    def copy_response_positions(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.positions]

    def copy_response_orders(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = [item for item in self.orders]
        if status:
            rows = [item for item in rows if str(item.get("status") or "") == status]
        return [self._copy_public_record(item) for item in rows]

    def copy_response_trades(self) -> list[dict[str, Any]]:
        return [self._copy_public_record(item) for item in self.trades]

    def _copy_public_record(self, item: Mapping[str, Any]) -> dict[str, Any]:
        row = {
            str(key): value
            for key, value in item.items()
            if not str(key).startswith("_stub_")
        }
        if not bool(item.get("_stub_expose_qtoid", True)):
            row.pop("qtoid", None)
        return row


def _coerce_submit_script(
    item: GatewaySubmitScript | Mapping[str, Any],
) -> GatewaySubmitScript:
    if isinstance(item, GatewaySubmitScript):
        return item
    return GatewaySubmitScript(**dict(item))


def _coerce_cancel_script(
    item: GatewayCancelScript | Mapping[str, Any],
) -> GatewayCancelScript:
    if isinstance(item, GatewayCancelScript):
        return item
    return GatewayCancelScript(**dict(item))


def _normalize_scenario_obj(scenario: GatewayScenario) -> GatewayScenario:
    scenario.submit_scripts = [
        _coerce_submit_script(item) for item in scenario.submit_scripts
    ]
    scenario.cancel_scripts = [
        _coerce_cancel_script(item) for item in scenario.cancel_scripts
    ]
    return scenario


def _scenario_from_mapping(data: Mapping[str, Any]) -> GatewayScenario:
    values = dict(data)
    values["submit_scripts"] = [
        _coerce_submit_script(item) for item in values.get("submit_scripts", [])
    ]
    values["cancel_scripts"] = [
        _coerce_cancel_script(item) for item in values.get("cancel_scripts", [])
    ]
    return GatewayScenario(**values)


@dataclass
class GatewayStubState:
    prefix: str
    scenario: GatewayScenario
    api_key: str = "stub-api-key"
    lock: threading.RLock = field(default_factory=threading.RLock)

    def submit_order(self, side: str, form: Mapping[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.scenario.reject_next_orders:
                return {
                    "success": False,
                    "error": self.scenario.reject_next_orders.pop(0),
                }
            script = self._pop_submit_script(side, form)
            if script is not None:
                return self._apply_submit_script(script, side, form)
            return self._apply_default_submit(side, form)

    def _apply_default_submit(
        self, side: str, form: Mapping[str, Any]
    ) -> dict[str, Any]:
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
                trade = {
                    "tid": f"T{len(self.scenario.trades) + 1}",
                    "qtoid": qtoid,
                    "order_id": qtoid,
                    "symbol": symbol,
                    "side": side,
                    "shares": shares,
                    "price": price,
                    "amount": shares * price,
                    "time": order["time"],
                }
                self.scenario.trades.append(trade)
                self._apply_trade_state([trade])
            return {"success": True, "qtoid": qtoid, "order_id": qtoid}

    def cancel_order(self, qtoid: str) -> dict[str, Any]:
        with self.lock:
            order = self._find_order(qtoid)
            external_order_id = str(order.get("order_id") or "") if order else None
            script = self._pop_cancel_script(qtoid, external_order_id)
            if script is not None:
                return self._apply_cancel_script(script, qtoid, order)
            if order is not None:
                order["status"] = "cancelled"
                return {"success": True, "qtoid": str(order.get("qtoid") or qtoid)}
        return {"success": False, "error": f"unknown order: {qtoid}"}

    def _pop_submit_script(
        self, side: str, form: Mapping[str, Any]
    ) -> GatewaySubmitScript | None:
        for index, script in enumerate(self.scenario.submit_scripts):
            if script.matches(side, form):
                return self.scenario.submit_scripts.pop(index)
        return None

    def _pop_cancel_script(
        self, qtoid: str, order_id: str | None
    ) -> GatewayCancelScript | None:
        for index, script in enumerate(self.scenario.cancel_scripts):
            if script.matches(qtoid, order_id):
                return self.scenario.cancel_scripts.pop(index)
        return None

    def _apply_submit_script(
        self,
        script: GatewaySubmitScript,
        side: str,
        form: Mapping[str, Any],
    ) -> dict[str, Any]:
        qtoid = str(form.get("qtoid") or script.response.get("qtoid") or uuid.uuid4())
        result = {"success": True, **dict(script.response)}
        external_order_id = self._resolve_external_order_id(result, script.order, qtoid)
        if result.get("success"):
            order = self._build_scripted_order(
                script=script,
                side=side,
                form=form,
                qtoid=qtoid,
                order_id=external_order_id,
            )
            self.scenario.orders.append(order)
            built_trades: list[dict[str, Any]] = []
            for index, trade_payload in enumerate(script.trades, start=1):
                trade = self._build_scripted_trade(
                    payload=trade_payload,
                    side=side,
                    form=form,
                    qtoid=qtoid,
                    order_id=external_order_id,
                    expose_qtoid=script.expose_trade_qtoid,
                    index=index,
                )
                built_trades.append(trade)
                self.scenario.trades.append(trade)
            self._apply_scripted_state(script, built_trades)
        if not any(key in result for key in ("qtoid", "order_id", "foid", "external_order_id")):
            result["qtoid"] = qtoid
            result["order_id"] = external_order_id
        return result

    def _apply_cancel_script(
        self,
        script: GatewayCancelScript,
        requested_qtoid: str,
        order: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = {"success": True, **dict(script.response)}
        if result.get("success") and order is not None and script.order_status:
            order["status"] = script.order_status
        if "qtoid" not in result and not script.response:
            result["qtoid"] = str(order.get("qtoid") or requested_qtoid) if order else requested_qtoid
        return result

    def _find_order(self, qtoid: str) -> dict[str, Any] | None:
        for order in self.scenario.orders:
            if str(order.get("qtoid") or "") == qtoid:
                return order
            if str(order.get("order_id") or "") == qtoid:
                return order
        return None

    def _resolve_external_order_id(
        self,
        response: Mapping[str, Any],
        order_payload: Mapping[str, Any],
        qtoid: str,
    ) -> str:
        for source in (response, order_payload):
            for key in ("order_id", "foid", "external_order_id"):
                value = source.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return qtoid

    def _build_scripted_order(
        self,
        *,
        script: GatewaySubmitScript,
        side: str,
        form: Mapping[str, Any],
        qtoid: str,
        order_id: str,
    ) -> dict[str, Any]:
        shares = int(float(script.order.get("shares") or form.get("shares") or 0))
        price = float(script.order.get("price") or form.get("price") or 0)
        trade_shares = sum(float(item.get("shares") or 0) for item in script.trades)
        filled = float(script.order["filled"]) if "filled" in script.order else trade_shares
        order = {
            "qtoid": qtoid,
            "order_id": order_id,
            "symbol": str(form.get("symbol") or script.order.get("symbol") or ""),
            "side": str(script.order.get("side") or side),
            "shares": shares,
            "price": price,
            "filled": filled,
            "status": str(script.order.get("status") or self._infer_order_status(shares, filled)),
            "strategy_id": str(form.get("strategy_id") or script.order.get("strategy_id") or ""),
            "time": str(script.order.get("time") or _now_text()),
            "_stub_expose_qtoid": script.expose_order_qtoid,
        }
        order.update(dict(script.order))
        order["qtoid"] = qtoid
        order["order_id"] = order_id
        order["_stub_expose_qtoid"] = script.expose_order_qtoid
        return order

    def _build_scripted_trade(
        self,
        *,
        payload: Mapping[str, Any],
        side: str,
        form: Mapping[str, Any],
        qtoid: str,
        order_id: str,
        expose_qtoid: bool,
        index: int,
    ) -> dict[str, Any]:
        shares = float(payload.get("shares") or form.get("shares") or 0)
        price = float(payload.get("price") or form.get("price") or 0)
        trade = {
            "tid": str(payload.get("tid") or f"T{len(self.scenario.trades) + index}"),
            "qtoid": qtoid,
            "order_id": order_id,
            "symbol": str(payload.get("symbol") or form.get("symbol") or ""),
            "side": str(payload.get("side") or side),
            "shares": shares,
            "price": price,
            "amount": float(payload.get("amount") or shares * price),
            "time": str(payload.get("time") or _now_text()),
            "_stub_expose_qtoid": expose_qtoid,
        }
        trade.update(dict(payload))
        trade["qtoid"] = qtoid
        trade["order_id"] = order_id
        trade["_stub_expose_qtoid"] = expose_qtoid
        return trade

    def _infer_order_status(self, shares: int, filled: float) -> str:
        if shares > 0 and filled >= shares:
            return "filled"
        if filled > 0:
            return "partial"
        return "submitted"

    def _apply_scripted_state(
        self,
        script: GatewaySubmitScript,
        trades: list[dict[str, Any]],
    ) -> None:
        if script.asset_after is not None:
            self.scenario.asset = dict(script.asset_after)
        elif trades:
            self._apply_trade_state(trades)
        if script.positions_after is not None:
            self.scenario.positions = [dict(item) for item in script.positions_after]

    def _apply_trade_state(self, trades: list[dict[str, Any]]) -> None:
        positions = {
            str(item.get("symbol") or ""): dict(item)
            for item in self.scenario.positions
            if str(item.get("symbol") or "").strip()
        }
        cash = float(self.scenario.asset.get("cash") or 0)

        for trade in trades:
            symbol = str(trade.get("symbol") or "").strip()
            if not symbol:
                continue
            side = _normalize_side_text(str(trade.get("side") or "")) or ""
            shares = float(trade.get("shares") or 0)
            price = float(trade.get("price") or 0)
            amount = float(trade.get("amount") or shares * price)
            fee = float(trade.get("fee") or 0)

            position = positions.get(
                symbol,
                {
                    "symbol": symbol,
                    "shares": 0.0,
                    "avail": 0.0,
                    "cost": price,
                    "market_value": 0.0,
                },
            )
            current_shares = float(position.get("shares") or 0)
            current_avail = float(position.get("avail") or current_shares)
            current_cost = float(position.get("cost") or 0)

            if side == "buy":
                new_shares = current_shares + shares
                if new_shares > 0:
                    position["cost"] = (
                        current_shares * current_cost + amount + fee
                    ) / new_shares
                position["shares"] = new_shares
                position["avail"] = current_avail + shares
                cash -= amount + fee
            elif side == "sell":
                new_shares = max(current_shares - shares, 0.0)
                position["shares"] = new_shares
                position["avail"] = max(current_avail - shares, 0.0)
                cash += amount - fee
            else:
                continue

            position["market_value"] = float(position.get("shares") or 0) * price
            if float(position.get("shares") or 0) <= 0:
                positions.pop(symbol, None)
            else:
                positions[symbol] = position

        market_value = sum(float(item.get("market_value") or 0) for item in positions.values())
        asset = dict(self.scenario.asset)
        asset["cash"] = cash
        asset["market_value"] = market_value
        asset["total"] = cash + market_value
        asset.setdefault("principal", float(asset.get("principal") or 0))
        asset.setdefault("frozen_cash", float(asset.get("frozen_cash") or 0))
        self.scenario.asset = asset
        self.scenario.positions = list(positions.values())


def _constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison to avoid leaking key length via timing."""
    a_bytes = a.encode("utf-8")
    b_bytes = b.encode("utf-8")
    return hmac.compare_digest(a_bytes, b_bytes)


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


def _ws_frame(opcode: int, payload: bytes = b"") -> bytes:
    size = len(payload)
    if size <= 125:
        header = bytes([0x80 | (opcode & 0x0F), size])
    elif size <= 65535:
        header = bytes([0x80 | (opcode & 0x0F), 126]) + size.to_bytes(2, "big")
    else:
        header = bytes([0x80 | (opcode & 0x0F), 127]) + size.to_bytes(8, "big")
    return header + payload


def _ws_text_frame(payload: Mapping[str, Any]) -> bytes:
    body = _json_bytes(payload)
    return _ws_frame(0x1, body)


def _read_exact(connection: socket.socket, size: int) -> bytes | None:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def _read_ws_frame(connection: socket.socket) -> tuple[int, bytes] | None:
    header = _read_exact(connection, 2)
    if header is None:
        return None

    first, second = header
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    size = second & 0x7F

    if size == 126:
        extended = _read_exact(connection, 2)
        if extended is None:
            return None
        size = int.from_bytes(extended, "big")
    elif size == 127:
        extended = _read_exact(connection, 8)
        if extended is None:
            return None
        size = int.from_bytes(extended, "big")

    mask = _read_exact(connection, 4) if masked else b""
    if masked and mask is None:
        return None

    payload = _read_exact(connection, size)
    if payload is None:
        return None

    if masked:
        mask_bytes = mask or b""
        payload = bytes(
            byte ^ mask_bytes[index % 4] for index, byte in enumerate(payload)
        )
    return opcode, payload


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
            if path == _prefix_path(state.prefix, "/api/ping"):
                if state.api_key:
                    presented = self.headers.get("X-API-Key", "")
                    if not _constant_time_equals(presented, state.api_key):
                        self._send_json(
                            {"code": 401, "message": "API key 无效或已吊销"},
                            status=HTTPStatus.UNAUTHORIZED,
                        )
                        return
                self._send_json(
                    {"code": 0, "message": "ok", "data": {"ok": True}}
                )
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

            self.connection.settimeout(1.0)
            try:
                while True:
                    try:
                        frame = _read_ws_frame(self.connection)
                    except socket.timeout:
                        continue
                    if frame is None:
                        break
                    opcode, payload = frame
                    if opcode == 0x8:
                        try:
                            self.connection.sendall(_ws_frame(0x8, payload))
                        except OSError:
                            pass
                        break
                    if opcode == 0x9:
                        self.connection.sendall(_ws_frame(0xA, payload))
            except OSError:
                pass
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
    api_key: str = "stub-api-key",
) -> GatewayStub:
    """Start a local gateway stub with auth, trade, query, cancel and quote paths."""
    normalized_prefix = _normalize_prefix(prefix)
    if scenario is None:
        scenario_obj = GatewayScenario()
    elif isinstance(scenario, GatewayScenario):
        scenario_obj = _normalize_scenario_obj(scenario)
    else:
        scenario_obj = _scenario_from_mapping(scenario)
    state = GatewayStubState(
        prefix=normalized_prefix,
        scenario=scenario_obj,
        api_key=api_key,
    )
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
    api_key: str = "stub-api-key",
) -> Iterator[GatewayStub]:
    """Yield a running scriptable gateway stub and stop it automatically."""
    stub = start_gateway_stub(
        host=host, prefix=prefix, scenario=scenario, api_key=api_key
    )
    try:
        yield stub
    finally:
        stub.stop()
