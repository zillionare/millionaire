"""主题配置模块

统一管理应用的主题颜色和样式。
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Script, Style
from monsterui.all import Theme

from quantide.web.design_system import (
    BRAND,
    BRAND_DARK,
    BRAND_LIGHT,
    GRAY_100,
    GRAY_200,
    GRAY_900,
    DesignSystem,
)

#: 兼容旧代码从 theme 直接导入
PRIMARY_COLOR = BRAND
PRIMARY_DARK = BRAND_DARK
PRIMARY_LIGHT = BRAND_LIGHT
SECONDARY_COLOR = GRAY_100
TEXT_COLOR = GRAY_900
BORDER_COLOR = GRAY_200


class AppTheme:
    """应用主题配置类"""

    @staticmethod
    def headers() -> list[Any]:
        """获取主题 headers（CSS 和脚本）"""
        # 使用 monsterui 默认主题（黑白灰），禁用 Theme.red 的红色渐变背景
        base_headers = Theme.neutral.headers()

        # 设计系统全局样式（黑白灰 + 品牌红强调）
        design_css = DesignSystem.css()

        # 项目级覆盖（兼容既有类名）
        override_css = Style("""
            /* 品牌色覆盖（兼容旧代码中的 --p 变量） */
            :root {
                --p: 0.6 0.19 34;      /* DaisyUI primary: 红 */
                --pf: 0.6 0.19 30;     /* primary focus */
                --pc: 0 0% 100%;       /* primary content */
            }

            /* 全局面包屑 / 侧边栏微调 */
            .q-breadcrumb { font-size: 14px; }
            #layout-sidebar a { color: var(--fg); }
            #layout-sidebar a:hover { color: var(--brand); }

            /* <details> 原生箭头统一隐藏，避免与自定义 chevron 重复 */
            summary { list-style: none; }
            summary::-webkit-details-marker { display: none; }
            summary::marker { content: ""; }
            #layout-sidebar summary::before,
            #layout-sidebar summary::after { content: none !important; display: none !important; }
        """)

        # HTMX
        htmx_script = Script(src="https://unpkg.com/htmx.org@1.9.12")

        return list(base_headers) + [design_css, override_css, htmx_script]


__all__ = ["AppTheme"]
