"""NFR-0030 错误降级.

定义数据源不可用与网关断开时的 UI 降级文案/结构, 确保用户看到失败提示
而非空白页.

AC-NFR0030-1: 数据源不可用 -> "数据加载失败, 正在重试..." + 自动重试倒计时.
AC-NFR0030-2: trade-gateway 断开 -> 黄色横幅 + 红色 ⚠ 图标/文字 + 重试按钮.
"""

from __future__ import annotations

DEFAULT_RETRY_COUNTDOWN_SECONDS = 5


def data_unavailable_message(seconds_until_retry: int) -> str:
    """AC-NFR0030-1: 数据源不可用时的表格上方提示文案.

    Args:
        seconds_until_retry: 距离下次自动重试的秒数.

    Returns:
        提示文案.
    """
    return f"数据加载失败, 正在重试... ({seconds_until_retry} 秒后重试)"


def gateway_disconnect_banner() -> dict[str, object]:
    """AC-NFR0030-2: 网关断开横幅配置.

    Returns:
        包含背景色、图标、文字颜色、重试按钮等字段的字典.
    """
    return {
        "background": "yellow",
        "icon": "⚠",
        "icon_color": "red",
        "text_color": "red",
        "message": "网关断开",
        "retry_button": True,
    }


__all__ = [
    "DEFAULT_RETRY_COUNTDOWN_SECONDS",
    "data_unavailable_message",
    "gateway_disconnect_banner",
]
