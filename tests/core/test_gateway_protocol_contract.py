"""qmt-gateway 通讯契约测试（spec 12）。"""

from unittest.mock import patch

import pytest

from quantide.core.runtime.gateway_client import (
    GatewayClient,
    GatewayProtocolError,
    _assert_json_content_type,
)


class TestAssertJsonContentType:

    @pytest.mark.parametrize(
        "ct",
        [
            "application/json",
            "application/json; charset=utf-8",
            "text/plain",
            "text/json",
            "application/octet-stream",
            "",
        ],
    )
    def test_accepted_content_types(self, ct: str) -> None:
        _assert_json_content_type("http://x/y", ct)

    @pytest.mark.parametrize(
        "ct",
        [
            "text/html",
            "text/html; charset=utf-8",
            "application/xhtml+xml",
        ],
    )
    def test_html_responses_are_rejected(self, ct: str) -> None:
        with pytest.raises(GatewayProtocolError, match="htmx"):
            _assert_json_content_type("http://x/y", ct)

    def test_unknown_content_type_raises(self) -> None:
        with pytest.raises(GatewayProtocolError, match="未预期"):
            _assert_json_content_type("http://x/y", "application/x-foo")


class _FakeResponse:

    def __init__(self, body: str = "", content_type: str = "application/json", status: int = 200):
        self._body = body.encode("utf-8") if isinstance(body, str) else body
        self.headers = {"Content-Type": content_type}
        self.status = status

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestGatewayClientProtocolGuard:

    def test_get_json_rejects_html_response(self) -> None:
        client = GatewayClient("http://x", "u", "p", timeout=1.0)
        client._logged_in = True
        html_body = "<html><body>positions</body></html>"

        with patch.object(client, "ensure_login"), patch.object(
            client._opener, "open", return_value=_FakeResponse(html_body, "text/html")
        ):
            with pytest.raises(GatewayProtocolError, match="htmx"):
                client.get_json("/api/trade/positions")

    def test_get_json_accepts_json_response(self) -> None:
        client = GatewayClient("http://x", "u", "p", timeout=1.0)
        client._logged_in = True

        with patch.object(client, "ensure_login"), patch.object(
            client._opener, "open", return_value=_FakeResponse("[{\"asset\": \"601398\"}]", "application/json")
        ):
            data = client.get_json("/api/trade/positions")
        assert data == [{"asset": "601398"}]

    def test_post_form_rejects_html_response(self) -> None:
        client = GatewayClient("http://x", "u", "p", timeout=1.0)
        client._logged_in = True

        with patch.object(client, "ensure_login"), patch.object(
            client._opener, "open", return_value=_FakeResponse("<html>error</html>", "text/html")
        ):
            with pytest.raises(GatewayProtocolError, match="htmx"):
                client.post_form("/api/trade/buy", {"asset": "601398", "shares": 100, "price": 5.0})

    def test_get_json_missing_content_type_logs_but_accepts(self) -> None:
        client = GatewayClient("http://x", "u", "p", timeout=1.0)
        client._logged_in = True

        with patch.object(client, "ensure_login"), patch.object(
            client._opener, "open", return_value=_FakeResponse("[]", "")
        ):
            data = client.get_json("/api/trade/positions")
        assert data == []


class TestAuditNoHtmxEndpointsUsed:

    @pytest.mark.parametrize(
        "needle",
        ["?view=table", "?view=html", "?view=card", "Accept: text/html"],
    )
    def test_no_htmx_request_patterns_in_quantide_source(self, needle: str) -> None:
        import subprocess
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent.parent
        result = subprocess.run(
            ["grep", "-r", "--exclude-dir=__pycache__", "--exclude-dir=.venv",
             "--exclude-dir=.git", "-l", needle, str(repo_root / "quantide")],
            capture_output=True,
            text=True,
        )
        matches = [p for p in result.stdout.splitlines() if p.strip()]
        assert not matches, f"spec 12 禁止的 htmx 请求模式 {needle!r} 出现在: {matches}"
