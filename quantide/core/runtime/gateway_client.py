"""qmt-gateway 远程调用客户端."""

import json
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any

from loguru import logger

from quantide.config.settings import get_settings


class GatewayProtocolError(RuntimeError):
    """与 qmt-gateway 通讯契约被违反时抛（见 .dev/specs/12-gateway-protocol-contract.md）。"""


def _assert_json_content_type(url: str, content_type: str) -> None:
    """校验响应 Content-Type 是 JSON 或 text/plain；htmx/text/html 一律拒绝。

    Args:
        url: 请求 URL，仅用于日志。
        content_type: 响应头中的 Content-Type（可能为空）。

    Raises:
        GatewayProtocolError: 收到 text/html 等禁止的响应类型。
    """
    ct = (content_type or "").lower().split(";")[0].strip()
    if not ct:
        logger.warning("gateway response missing Content-Type: {}", url)
        return
    if ct in {"application/json", "text/plain", "text/json", "application/octet-stream"}:
        return
    if "html" in ct:
        raise GatewayProtocolError(
            f"qmt-gateway 端点返回了 htmx/text/html（违反 spec 12 协议契约）：{url} Content-Type={ct!r}。"
            " quantide 端不应请求 htmx 端点；请改用对应的 JSON 端点。"
        )
    raise GatewayProtocolError(
        f"qmt-gateway 返回了未预期的 Content-Type：{url} Content-Type={ct!r}"
    )


class GatewayClient:
    """qmt-gateway HTTP 会话客户端."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: float = 10.0,
    ):
        """初始化客户端.

        Args:
            base_url: 网关地址。
            username: 用户名。
            password: 密码。
            timeout: 超时秒数。
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._cookies = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookies)
        )
        self._logged_in = False

    @classmethod
    def from_config(cls) -> "GatewayClient":
        """从配置创建客户端."""
        runtime = get_settings()
        return cls(
            base_url=runtime.gateway_base_url,
            username=runtime.gateway_username,
            password=runtime.gateway_password,
            timeout=float(runtime.gateway_timeout),
        )

    def ensure_login(self) -> None:
        """确保会话已登录."""
        if self._logged_in:
            return
        form = urllib.parse.urlencode(
            {
                "username": self.username,
                "password": self.password,
                "auto_login": "false",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}/auth/login",
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with self._opener.open(req, timeout=self.timeout) as resp:
            code = resp.getcode()
            if code < 200 or code >= 400:
                raise RuntimeError(f"gateway login failed: {code}")
        self._logged_in = True

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """调用 GET 接口.

        校验 Content-Type 必须为 JSON 或 text/plain（spec 12）。htmx 响应抛 GatewayProtocolError。
        """
        self.ensure_login()
        query = ""
        if params:
            query = "?" + urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}{query}"
        req = urllib.request.Request(
            url=url,
            method="GET",
        )
        with self._opener.open(req, timeout=self.timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            _assert_json_content_type(url, content_type)
            body = resp.read().decode("utf-8")
            if not body:
                return None
            return json.loads(body)

    def post_form(self, path: str, data: dict[str, Any]) -> Any:
        """调用 POST 表单接口.

        校验 Content-Type 必须为 JSON 或 text/plain（spec 12）。htmx 响应抛 GatewayProtocolError。
        """
        self.ensure_login()
        form = urllib.parse.urlencode(data).encode("utf-8")
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url=url,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with self._opener.open(req, timeout=self.timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            _assert_json_content_type(url, content_type)
            body = resp.read().decode("utf-8")
            if not body:
                return None
            return json.loads(body)

    def cookie_header(self) -> str:
        """导出 Cookie 头字符串."""
        items = []
        for c in self._cookies:
            items.append(f"{c.name}={c.value}")
        return "; ".join(items)

    def ws_url(self, path: str) -> str:
        """生成 WS 地址."""
        base = self.base_url
        if base.startswith("https://"):
            return "wss://" + base.removeprefix("https://").rstrip("/") + path
        if base.startswith("http://"):
            return "ws://" + base.removeprefix("http://").rstrip("/") + path
        return "ws://" + base.rstrip("/") + path
