"""NFR-0040 视觉与组件规范.

定义 UI 设计令牌与校验函数, 确保全站视觉一致性.

AC-NFR0040-1: 字体尺寸 (page 24px / section 18px / body 14px / table 13px / helper 12px).
AC-NFR0040-2: 按钮风格统一 (主操作中性深色实心, 次操作描边, 危险操作红描边+文字).
AC-NFR0040-3: Modal 居中浮层 + 半透明遮罩 + 关闭按钮.
AC-NFR0040-4: 语义色彩 5 色一致.
AC-NFR0040-5: 8px 基准网格.
AC-NFR0040-6: 统一圆角 (按钮 4px / 卡片 8px / Modal 12px).
AC-NFR0040-7: 禁止大面积红色背景.
"""

from __future__ import annotations

TYPOGRAPHY: dict[str, str] = {
    "page_title": "24px",
    "section_title": "18px",
    "body": "14px",
    "table": "13px",
    "helper": "12px",
}

BUTTON_RADIUS_PX = 4
CARD_RADIUS_PX = 8
MODAL_RADIUS_PX = 12

SEMANTIC_COLORS: dict[str, str] = {
    "success": "green",
    "error": "red",
    "warning": "yellow",
    "info": "blue",
    "neutral": "gray",
}

SPACING_GRID: frozenset[int] = frozenset({4, 8, 16, 24, 32})

_RED_BACKGROUND_VALUES: frozenset[str] = frozenset({"red", "#ff0000", "#f00"})


def button_style(variant: str) -> dict[str, object]:
    """返回指定按钮变体的风格配置.

    Args:
        variant: primary / secondary / danger.

    Returns:
        风格配置字典.
    """
    styles: dict[str, dict[str, object]] = {
        "primary": {
            "background": "neutral-dark",
            "color": "white",
            "border_radius_px": BUTTON_RADIUS_PX,
        },
        "secondary": {
            "variant": "outline",
            "border_radius_px": BUTTON_RADIUS_PX,
        },
        "danger": {
            "background": None,
            "border_color": "red",
            "color": "red",
            "border_radius_px": BUTTON_RADIUS_PX,
        },
    }
    return styles.get(variant, styles["secondary"])


def modal_spec() -> dict[str, object]:
    """AC-NFR0040-3: 返回 Modal 规范配置."""
    return {
        "position": "center",
        "overlay": True,
        "overlay_opacity": 0.5,
        "close_button": True,
        "border_radius_px": MODAL_RADIUS_PX,
    }


def is_spacing_grid_compliant(value_px: int) -> bool:
    """判断间距是否符合 8px 基准网格.

    Args:
        value_px: 间距像素值.

    Returns:
        True 当 value_px 是 8 的倍数或属于常用网格值.
    """
    return value_px in SPACING_GRID or value_px % 8 == 0


def is_valid_background_color(color: str | None) -> bool:
    """AC-NFR0040-7: 判断背景色是否为大面�不允许的红色.

    Args:
        color: 背景色值或名称.

    Returns:
        False 当 color 为大面积红色; True 表示可接受.
    """
    if color is None:
        return True
    return color.lower() not in _RED_BACKGROUND_VALUES


__all__ = [
    "BUTTON_RADIUS_PX",
    "CARD_RADIUS_PX",
    "MODAL_RADIUS_PX",
    "SEMANTIC_COLORS",
    "SPACING_GRID",
    "TYPOGRAPHY",
    "button_style",
    "is_spacing_grid_compliant",
    "is_valid_background_color",
    "modal_spec",
]
