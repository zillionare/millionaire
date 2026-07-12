"""FR-0180 功能降级状态机.

定义 A 类 (永久, 无网关) 与 B 类 (临时, 网关偶发不可连) 降级的判定规则、
入口禁用规则、tooltip 文案与 banner 颜色规范.

对应 acceptance.md AC-FR0180-1~23.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class DegradationClass(str, Enum):
    """降级类别.

    A: 永久降级 (无网关配置), 配置后立即解除.
    B: 临时降级 (有网关但偶发不可连), 永不升级为 A.
    """

    A = "A"
    B = "B"


@dataclass
class DegradationState:
    """降级判定输入状态.

    Attributes:
        gateway_configured: 服务端是否已配置 gateway (A 类判定依据).
        gateway_online: 已配置的 gateway 当前是否可连 (B 类判定依据).
    """

    gateway_configured: bool
    gateway_online: bool


@dataclass
class GatewayConfig:
    """FR-0340 网关配置 (interfaces.md §4.6).

    Attributes:
        server: 非 host/IP.
        port: 1..65535.
        url_prefix: 以 / 开头.
        api_key: 服务端保存, 不写 localStorage.
        timeout_seconds: >=1.
    """

    server: str
    port: int
    url_prefix: str
    api_key: str
    timeout_seconds: int

    def is_valid(self) -> bool:
        """校验配置字段是否合法.

        Returns:
            True 当且仅当所有字段满足 interfaces.md §4.6 约束.
        """
        if not self.server.strip():
            return False
        if not (1 <= int(self.port) <= 65535):
            return False
        if not self.url_prefix.startswith("/"):
            return False
        if not self.api_key:
            return False
        if int(self.timeout_seconds) < 1:
            return False
        return True


_TRADE_ENTRANCES_DEPENDENT_ON_GATEWAY: frozenset[str] = frozenset(
    {
        "trade_live",
        "trade_paper",
        "promote_to_live",
        "promote_to_paper",
        "live_order",
        "live_cancel",
    }
)


def classify_degradation(state: DegradationState) -> DegradationClass | None:
    """根据 gateway 状态判定降级类别.

    Args:
        state: 当前 gateway 配置与连接状态.

    Returns:
        DegradationClass.A (无网关), DegradationClass.B (有网关但断线), 或 None (正常).
    """
    if not state.gateway_configured:
        return DegradationClass.A
    if not state.gateway_online:
        return DegradationClass.B
    return None


def entrance_disabled(entrance: str, degradation: DegradationClass | None) -> bool:
    """判断指定入口是否因降级被禁用.

    Args:
        entrance: 入口标识 (见 _TRADE_ENTRANCES_DEPENDENT_ON_GATEWAY).
        degradation: 当前降级类别.

    Returns:
        True 当 A 类降级且入口依赖 gateway.
    """
    if degradation != DegradationClass.A:
        return False
    return entrance in _TRADE_ENTRANCES_DEPENDENT_ON_GATEWAY


def is_trade_entrance_available(degradation: DegradationClass | None) -> bool:
    """AC-17: 顶栏'交易'菜单在 A 类降级时禁用.

    Args:
        degradation: 当前降级类别.

    Returns:
        True 当非 A 类降级.
    """
    return degradation != DegradationClass.A


def is_backtest_available(degradation: DegradationClass | None) -> bool:
    """AC-5, AC-19: 回测不依赖 gateway, 任何降级状态下仍可用.

    Args:
        degradation: 当前降级类别.

    Returns:
        始终 True.
    """
    return True


def is_gateway_management_available(degradation: DegradationClass | None) -> bool:
    """AC-7: 网关管理在 A 类降级时仍可用 (用来配置 gateway).

    Args:
        degradation: 当前降级类别.

    Returns:
        始终 True.
    """
    return True


def tooltip_message(degradation: DegradationClass | None) -> str | None:
    """AC-1, AC-18: A 类降级时入口 hover tooltip 文案.

    Args:
        degradation: 当前降级类别.

    Returns:
        A 类降级返回提示文案; 其他返回 None.
    """
    if degradation != DegradationClass.A:
        return None
    return "此功能因交易网关未配置而无法使用"


def banner_colors(
    degradation: DegradationClass | None,
) -> dict[str, Literal["yellow", "red"]] | None:
    """AC-9, AC-20: B 类降级 banner 颜色规范.

    banner 背景黄色 (warning), 文字+图标红色 (error 强调), 满足 NFR-0040 禁止大面积红色背景.

    Args:
        degradation: 当前降级类别.

    Returns:
        B 类降级返回颜色字典; 其他返回 None.
    """
    if degradation != DegradationClass.B:
        return None
    return {"background": "yellow", "text": "red", "icon": "red"}


__all__ = [
    "DegradationClass",
    "DegradationState",
    "GatewayConfig",
    "banner_colors",
    "classify_degradation",
    "entrance_disabled",
    "is_backtest_available",
    "is_gateway_management_available",
    "is_trade_entrance_available",
    "tooltip_message",
]
