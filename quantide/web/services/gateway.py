"""FR-0340 网关管理服务.

定义网关配置校验、测试结果与保存结果 schema.

AC-3: 测试同时验证 (a) TCP 连接 + (b) API Key 鉴权.
AC-4: 保存前自动测试, 测试通过才能保存.
AC-5: 无删除网关按钮 (网关不能删除, 只能重新配置).
AC-6: 无添加第二个网关入口 (系统仅支持 1 个交易网关).
"""

from __future__ import annotations

from dataclasses import dataclass

GATEWAY_CONFIG_FIELDS: tuple[str, ...] = ("server", "port", "url_prefix", "api_key")
SINGLE_GATEWAY_ONLY: bool = True


class GatewayValidationError(ValueError):
    """网关配置校验错误."""


def validate_gateway_config(config: dict) -> bool:
    """AC-3: 校验网关配置字段.

    Args:
        config: 配置字典, 含 server / port / url_prefix / api_key / timeout_seconds.

    Returns:
        True 当所有字段满足 interfaces.md §4.6 约束.

    Raises:
        GatewayValidationError: 当任一字段非法.
    """
    server = str(config.get("server") or "").strip()
    if not server:
        raise GatewayValidationError("服务器不能为空")
    port = int(config.get("port") or 0)
    if not (1 <= port <= 65535):
        raise GatewayValidationError("端口必须在 1~65535")
    url_prefix = str(config.get("url_prefix") or "").strip()
    if not url_prefix.startswith("/"):
        raise GatewayValidationError("url_prefix 必须以 / 开头")
    if not str(config.get("api_key") or "").strip():
        raise GatewayValidationError("api_key 不能为空")
    if int(config.get("timeout_seconds") or 0) < 1:
        raise GatewayValidationError("超时必须 >= 1 秒")
    return True


@dataclass
class GatewayTestResult:
    """AC-3: 网关测试结果.

    Attributes:
        ok: 测试是否通过 (TCP + 鉴权均通过).
        tcp_connected: TCP 连接是否可达.
        auth_ok: API Key 鉴权是否有效.
        message: 结果消息 (成功/失败原因).
    """

    ok: bool
    tcp_connected: bool
    auth_ok: bool
    message: str


@dataclass
class GatewayConfigResult:
    """AC-4: 网关保存结果.

    Attributes:
        saved: 是否保存成功 (测试通过才为 True).
        message: 结果消息.
        tested: 是否已测试.
    """

    saved: bool
    message: str
    tested: bool


__all__ = [
    "GATEWAY_CONFIG_FIELDS",
    "GatewayConfigResult",
    "GatewayTestResult",
    "GatewayValidationError",
    "SINGLE_GATEWAY_ONLY",
    "validate_gateway_config",
]
