"""统一设计系统（设计令牌 + 全局样式）.

定义项目统一的视觉语言：

- **颜色**：黑白灰为主，红色只用于强调（品牌字、当前选中、错误、弹窗标题、买入按钮）；
- **字体**：系统字体栈，中文优先 PingFang/Hiragino，等宽数字；
- **边框/圆角**：卡片/按钮统一 8px 圆角 + 1px 灰色边框；
- **间距**：4px 基准（`space-1=4px`）；
- **阴影**：轻量灰阴影，无彩色阴影；
- **禁用**：禁止在页面中使用彩色渐变和除红/绿/灰外的强调色。

规则：
1. 正文/辅助文字用灰色梯度，标题用深灰；
2. 强调只用 `--brand`（红）；
3. 成功用灰绿，错误用红，警告用灰黄；
4. 买入红底白字，卖出绿底白字（交易页面专用）；
5. 弹窗标题为红底白字。
"""

from __future__ import annotations

from fasthtml.common import Script, Style

from quantide.web.template_assets import render_asset

#: 品牌红（唯一强调色）
BRAND = "#e41815"
BRAND_DARK = "#c91412"
BRAND_LIGHT = "#fff3f2"

#: 基础灰阶（参考 Vercel/Geist 风格）
GRAY_950 = "#0a0a0a"
GRAY_900 = "#171717"
GRAY_800 = "#262626"
GRAY_700 = "#404040"
GRAY_600 = "#525252"
GRAY_500 = "#737373"
GRAY_400 = "#a3a3a3"
GRAY_300 = "#d4d4d4"
GRAY_200 = "#e5e5e5"
GRAY_100 = "#f5f5f5"
GRAY_50 = "#fafafa"
WHITE = "#ffffff"

#: 功能色（不用于强调，只做语义）
GREEN = "#16a34a"  # 买入/盈利方向在中文语境通常用红；卖出/亏损用绿
GREEN_DARK = "#15803d"
AMBER = "#b45309"  # 中性警告（避免彩色背景）
RED = BRAND  # 错误/拒绝
RED_DARK = BRAND_DARK

#: 字体栈
FONT_STACK = (
    "'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Helvetica Neue',Helvetica,Arial,sans-serif"
)
MONO_STACK = "'SF Mono','Menlo','Monaco','Courier New',monospace"

#: 统一圆角
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 10

#: 阴影（灰阶，无彩色）
SHADOW_SM = "0 1px 2px rgba(0,0,0,0.05)"
SHADOW_MD = "0 4px 12px rgba(0,0,0,0.08)"
SHADOW_LG = "0 12px 32px rgba(0,0,0,0.12)"


def _css() -> str:
    """全局 CSS（使用 CSS 变量，页面组件引用这些令牌）。"""
    return render_asset(
        "design-system.css.tmpl",
        BRAND=BRAND,
        BRAND_DARK=BRAND_DARK,
        BRAND_LIGHT=BRAND_LIGHT,
        GRAY_900=GRAY_900,
        GRAY_600=GRAY_600,
        GRAY_500=GRAY_500,
        WHITE=WHITE,
        GRAY_50=GRAY_50,
        GRAY_100=GRAY_100,
        GRAY_200=GRAY_200,
        GRAY_300=GRAY_300,
        GREEN=GREEN,
        GREEN_DARK=GREEN_DARK,
        AMBER=AMBER,
        RADIUS_SM=RADIUS_SM,
        RADIUS_MD=RADIUS_MD,
        RADIUS_LG=RADIUS_LG,
        SHADOW_SM=SHADOW_SM,
        SHADOW_MD=SHADOW_MD,
        SHADOW_LG=SHADOW_LG,
        FONT_STACK=FONT_STACK,
        MONO_STACK=MONO_STACK,
    )


class DesignSystem:
    """设计系统入口。"""

    @staticmethod
    def css() -> Style:
        """全局样式（Style 元素，加入 headers）。"""
        return Style(_css())

    @staticmethod
    def js() -> Script:
        """全局脚本（当前为空，预留）。"""
        return Script("")

    @staticmethod
    def headers() -> list[Style]:
        """加入所有页面 headers 的设计系统资源。"""
        return [DesignSystem.css()]


__all__ = [
    "AMBER",
    "BRAND",
    "BRAND_DARK",
    "BRAND_LIGHT",
    "DesignSystem",
    "GRAY_50",
    "GRAY_100",
    "GRAY_200",
    "GRAY_300",
    "GRAY_400",
    "GRAY_500",
    "GRAY_600",
    "GRAY_700",
    "GRAY_800",
    "GRAY_900",
    "GRAY_950",
    "GREEN",
    "GREEN_DARK",
    "RED",
    "RED_DARK",
    "WHITE",
]
