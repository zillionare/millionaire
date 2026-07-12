"""NFR-0010 响应性预算.

定义 UI 响应性指标的可接受阈值, 供性能测试/监控调用.

AC-NFR0010-1: 冷启动首屏渲染 LCP < 2s (本地网络).
AC-NFR0010-2: 委托/成交列表实时刷新延迟 < 5s.
AC-NFR0010-3: 表格加载 10000 行后滚动 FPS >= 30.
"""

from __future__ import annotations

LCP_BUDGET_MS = 2000
REFRESH_LATENCY_BUDGET_S = 5.0
SCROLL_FPS_BUDGET = 30


def is_lcp_acceptable(lcp_ms: float) -> bool:
    """判断 LCP 是否满足预算.

    Args:
        lcp_ms: Largest Contentful Paint, 单位毫秒.

    Returns:
        True 当 lcp_ms 严格小于 2000.
    """
    return lcp_ms < LCP_BUDGET_MS


def is_refresh_latency_acceptable(delay_seconds: float) -> bool:
    """判断实时刷新延迟是否满足预算.

    Args:
        delay_seconds: 事件产生到 UI 反映的延迟, 单位秒.

    Returns:
        True 当 delay_seconds 严格小于 5.0.
    """
    return delay_seconds < REFRESH_LATENCY_BUDGET_S


def is_scroll_fps_acceptable(fps: float) -> bool:
    """判断滚动 FPS 是否满足预算.

    Args:
        fps: 每秒帧数.

    Returns:
        True 当 fps 大于等于 30.
    """
    return fps >= SCROLL_FPS_BUDGET


__all__ = [
    "LCP_BUDGET_MS",
    "REFRESH_LATENCY_BUDGET_S",
    "SCROLL_FPS_BUDGET",
    "is_lcp_acceptable",
    "is_refresh_latency_acceptable",
    "is_scroll_fps_acceptable",
]
