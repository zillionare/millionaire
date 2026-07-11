"""v0.2-003 FR-0203 gateway client contract tests."""

import json
from http.cookiejar import Cookie

import pytest

from quantide.core.runtime.gateway_client import GatewayClient, GatewayProtocolError


class Response:
    def __init__(self, body, content_type="application/json", code=200):
        self._body, self._code = body, code
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def getcode(self):
        return self._code

    def read(self):
        return self._body.encode()


class Opener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return next(self.responses)


def test_gateway_logs_in_once_and_parses_json_plain_text_and_empty_body():
    """FR-0203 AC-1/AC-2: login is reused and allowed responses parse deterministically."""
    client = GatewayClient("http://gateway", "user", "secret", timeout=3)
    opener = Opener([Response(""), Response(json.dumps({"ok": 1})), Response("", "text/plain")])
    client._opener = opener

    assert client.get_json("/orders", {"status": "open"}) == {"ok": 1}
    assert client.post_form("/cancel", {"id": "qt-1"}) is None

    assert [request.full_url for request, _ in opener.requests] == [
        "http://gateway/auth/login",
        "http://gateway/orders?status=open",
        "http://gateway/cancel",
    ]
    assert opener.requests[0][0].data == b"username=user&password=secret&auto_login=false"
    assert opener.requests[1][1] == 3


def test_gateway_rejects_html_and_exports_cookie_and_websocket_urls():
    """FR-0203 AC-2/AC-3: forbidden payloads fail and URL/cookie conversions retain data."""
    client = GatewayClient("https://gateway", "user", "secret")
    client._opener = Opener([Response(""), Response("<html/>", "text/html")])
    with pytest.raises(GatewayProtocolError):
        client.get_json("/orders")

    for name, value in (("session", "abc"), ("csrf", "def")):
        client._cookies.set_cookie(Cookie(0, name, value, None, False, "gateway", False, False, "/", True, False, None, True, None, None, {}))
    assert set(client.cookie_header().split("; ")) == {"session=abc", "csrf=def"}
    assert client.ws_url("/quotes") == "wss://gateway/quotes"
    assert GatewayClient("gateway", "u", "p").ws_url("/quotes") == "ws://gateway/quotes"
