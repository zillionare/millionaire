"""NFR-0050 局部刷新与失败隔离.

定义局部失败占位、独立重试与布局稳定性校验, 确保局部数据失败不导致整页失效
且刷新不造成跳动.

AC-NFR0050-1: 局部失败 -> 灰色占位 + 错误图标 + "加载失败" + 重试按钮.
AC-NFR0050-2: 局部刷新不得造成整页跳动/闪屏.
AC-NFR0050-3: 失败区域点击重试后独立重新加载.
"""

from __future__ import annotations

_LAYOUT_SHIFT_TOLERANCE_PX = 2


def partial_failure_placeholder(region_name: str) -> dict[str, object]:
    """AC-NFR0050-1: 返回局部失败区域的占位配置.

    Args:
        region_name: 区域名称 (例如 "orders").

    Returns:
        占位配置字典.
    """
    return {
        "region": region_name,
        "icon": "error_outline",
        "message": "加载失败",
        "sub_message": "请检查网络或稍后重试",
        "retry_button": True,
    }


def retry_region_payload(region_name: str, endpoint: str) -> dict[str, str]:
    """AC-NFR0050-3: 返回独立重试某区域的请求配置.

    Args:
        region_name: 区域名称/ID.
        endpoint: 重试请求地址.

    Returns:
        包含 target 与 url 的字典.
    """
    return {"target": region_name, "url": endpoint}


def assert_no_layout_shift(
    original_rect: dict[str, float],
    new_rect: dict[str, float],
    tolerance_px: float = _LAYOUT_SHIFT_TOLERANCE_PX,
) -> bool:
    """AC-NFR0050-2: 判断两次布局矩形变化是否在容差内.

    Args:
        original_rect: 刷新前矩形 (x, y, width, height).
        new_rect: 刷新后矩形.
        tolerance_px: 允许的像素偏差.

    Returns:
        True 当 x/y/width/height 变化均不超过容差.
    """
    for key in ("x", "y", "width", "height"):
        if abs(original_rect[key] - new_rect[key]) > tolerance_px:
            return False
    return True


def independent_region_id(page: str, region: str) -> str:
    """生成页面内独立区域 ID, 用于局部刷新定位.

    Args:
        page: 页面标识.
        region: 区域标识.

    Returns:
        稳定区域 ID.
    """
    return f"{page}__{region}"


__all__ = [
    "assert_no_layout_shift",
    "independent_region_id",
    "partial_failure_placeholder",
    "retry_region_payload",
]
