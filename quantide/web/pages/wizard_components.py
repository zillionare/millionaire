"""Wizard components."""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Div,
    P,
    Span,
)
from monsterui.all import *
from monsterui.all import (
    H3,
)

from quantide.config.branding import get_branding
from quantide.config.dev_stubs import (
    dev_stubs_enabled,
)
from quantide.config.features import supports_live_trading
from quantide.web.pages.wizard_state import (
    FONT_STYLES,
    PRIMARY_COLOR,
)


def _render_inline_error(message: str) -> Any:
    return Div(
        Div(
            Span("❌", cls="mr-2"),
            Span(message),
            cls="text-sm text-red-600 mt-3 flex items-center",
        ),
        id="wizard-error",
    )


def RequiredMark() -> Any:
    """必填项标记 - 红色星号"""
    return Span("*", style=FONT_STYLES["required"])


def InfoTooltip(tooltip_text: str) -> Any:
    """信息提示图标 - 鼠标悬停显示 tooltip

    Args:
        tooltip_text: 提示文本内容
    """
    return Span(
        "ⓘ",
        title=tooltip_text,
        style="color: #9ca3af; cursor: help; margin-left: 4px; font-size: 12px;",
        cls="tooltip-icon",
    )


def FormLabel(label: str, required: bool = False, tooltip: str | None = None) -> Any:
    """表单标签组件

    Args:
        label: 标签文本
        required: 是否为必填项
        tooltip: 可选的提示文本
    """
    children = [Span(label, style=FONT_STYLES["label"])]
    if required:
        children.append(RequiredMark())
    if tooltip:
        children.append(InfoTooltip(tooltip))
    return Div(*children, cls="mb-1")


def FormRow(
    label: str, input_component: Any, required: bool = False, tooltip: str | None = None
) -> Any:
    """横向排列的表单项（label 和 input 在同一行）

    Args:
        label: 标签文本
        input_component: 输入组件
        required: 是否为必填项
        tooltip: 可选的提示文本
    """
    label_children = [Span(label, style=FONT_STYLES["label"])]
    if required:
        label_children.append(RequiredMark())
    if tooltip:
        label_children.append(InfoTooltip(tooltip))

    return Div(
        Div(
            *label_children,
            cls="flex items-center gap-1",
            style="min-width: 100px; flex-shrink: 0;",
        ),
        Div(input_component, cls="flex-1"),
        cls="flex items-center gap-4 mb-4",
    )


def FormHint(text: str) -> Any:
    """表单提示文本"""
    return P(text, style=FONT_STYLES["hint"], cls="mt-1 mb-3")


def SectionTitle(text: str) -> Any:
    """章节标题"""
    return H3(text, cls="mb-4", style=f"{FONT_STYLES['title']} color: {PRIMARY_COLOR};")


def SectionDescription(text: str) -> Any:
    """章节描述"""
    return P(text, style=FONT_STYLES["description"], cls="mb-4")


def _wizard_step_meta() -> dict[int, dict[str, str]]:
    """Build step metadata using the active product brand."""
    product_name = get_branding().product_name
    return {
        1: {
            "title": f"欢迎使用 {product_name}!",
            "description": (
                f"{product_name} 是为量化人打造的集成开发环境 -- 数据、研究、回测、"
                + ("实盘。" if supports_live_trading() else "仿真。")
            ),
        },
        2: {
            "title": "运行环境",
            ("description"): (
                "配置行情数据存储位置、访问控制、监听端口和路径前缀。默认仅允许本机访问。"
                "配置数据库固定保存在系统配置目录。监听设置将在服务重启后生效。"
            ),
        },
        3: {
            "title": "设置管理员密码",
            ("description"): (
                "首次初始化时必须设置管理员密码。系统不会创建默认管理员或默认密码；当前版"
                "本固定使用 admin 作为管理员账号。"
            ),
        },
        4: {
            "title": "配置数据源",
            "description": "填写数据源与历史范围，下一步先检查所需接口权限，不会开始下载历史数据。",
        },
        5: {
            "title": "配置实时行情数据源",
            "description": (
                "用于仿真与实盘交易的实时行情，需要提供最新价格、当日涨跌停及复权所需数据。"
            ),
        },
        6: {
            "title": "数据准备与完成",
            "description": "确认配置后显式开始历史数据下载；完成后进入系统。",
        },
    }


def _get_step_meta(step: int) -> dict[str, str]:
    step_meta = _wizard_step_meta()
    meta = dict(step_meta.get(step, step_meta[1]))
    if not dev_stubs_enabled():
        return meta
    if step == 5:
        return {
            "title": "开发 Stub 交易网关",
            ("description"): (
                "当前进程已自动启动并启用本地 gateway "
                "stub，本步骤只展示运行时网关信息，不需要手工配置。"
            ),
        }
    if step == 4:
        return {
            "title": "导入开发 Stub 样本数据",
            ("description"): (
                "当前进程会直接把内置样本数据导入本地数据目录，不访问真实 "
                "Tushare，也不会触发首次下载对话框。将准备以下数据：证券日历、全A证券列表"
                "、历史日线样本（含复权因子与涨跌停价格）、ST 数据。"
            ),
        }
    return meta


def StepIndicator(current_step: int, steps: list[dict[str, Any]]) -> Any:
    """Render a vertical wizard timeline with a fixed layout grid."""
    elements = []
    for index, step in enumerate(steps, 1):
        elements.extend(_step_indicator_nodes(index, step, current_step, len(steps)))
    height = (len(steps) - 1) * 70 + 32 + 20
    return Div(
        *elements,
        cls="step-indicator-container",
        style=f"position: relative; width: 48px; height: {height}px; flex-shrink: 0;",
    )


def _step_indicator_nodes(index: Any, step: Any, current_step: Any, total: Any) -> Any:
    completed = step.get("completed", False)
    highlighted = index == current_step or completed
    top = (index - 1) * 70
    nodes = [
        Div(
            "✓" if completed else str(index),
            title=step["name"],
            style=f"""
            position: absolute;
            top: {top}px;
            left: 50%;
            transform: translateX(-50%);
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: {PRIMARY_COLOR if highlighted else "white"};
            color: {"white" if highlighted else "#9ca3af"};
            border: {"none" if highlighted else "2px solid #e5e7eb"};
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: {"600" if highlighted else "500"};
            z-index: 2;
        """,
        )
    ]
    if index < total:
        nodes.append(
            Div(
                style=f"""
            position: absolute;
            left: 50%;
            top: {top + 32}px;
            transform: translateX(-50%);
            width: 2px;
            height: 38px;
            background: {PRIMARY_COLOR if completed else "#e5e7eb"};
            z-index: 1;
        """
            )
        )
    return nodes
