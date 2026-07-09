"""NFR-0020 可访问性.

提供 WCAG 2.1 对比度计算, 用于校验主要文字与背景对比度 >= 4.5:1.

AC-NFR0020-1: 主要文字与背景对比度 >= 4.5:1 (WCAG AA).
"""

from __future__ import annotations

MIN_CONTRAST_RATIO = 4.5


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """将 3/6 位 hex 颜色转换为 RGB 元组.

    Args:
        hex_color: 例如 '#fff' 或 '#ffffff'.

    Returns:
        (r, g, b) 整数元组.
    """
    cleaned = hex_color.lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    return (
        int(cleaned[0:2], 16),
        int(cleaned[2:4], 16),
        int(cleaned[4:6], 16),
    )


def _channel_luminance(channel: int) -> float:
    """计算单个颜色通道的相对亮度分量."""
    s = channel / 255.0
    if s <= 0.03928:
        return s / 12.92
    return ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """计算 RGB 颜色的相对亮度 (WCAG 定义).

    Args:
        rgb: (r, g, b) 整数元组.

    Returns:
        相对亮度 (0.0 ~ 1.0).
    """
    r, g, b = rgb
    return (
        0.2126 * _channel_luminance(r)
        + 0.7152 * _channel_luminance(g)
        + 0.0722 * _channel_luminance(b)
    )


def contrast_ratio(foreground: str, background: str) -> float:
    """计算两个 hex 颜色的对比度.

    Args:
        foreground: 前景色 hex.
        background: 背景色 hex.

    Returns:
        对比度比值.
    """
    lum1 = relative_luminance(hex_to_rgb(foreground))
    lum2 = relative_luminance(hex_to_rgb(background))
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def is_contrast_acceptable(foreground: str, background: str) -> bool:
    """判断对比度是否满足 WCAG AA.

    Args:
        foreground: 前景色 hex.
        background: 背景色 hex.

    Returns:
        True 当对比度 >= 4.5.
    """
    return contrast_ratio(foreground, background) >= MIN_CONTRAST_RATIO


__all__ = [
    "MIN_CONTRAST_RATIO",
    "contrast_ratio",
    "hex_to_rgb",
    "is_contrast_acceptable",
    "relative_luminance",
]
