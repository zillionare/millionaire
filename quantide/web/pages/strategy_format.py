"""Strategy format."""

import datetime
from typing import Any

import fasthtml.common as fh
from fasthtml.common import *
from fasthtml.common import (
    Div,
    Script,
    Span,
    Style,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    Td,
)

from quantide.core.strategy_config import stored_strategy_config
from quantide.web.components.modal import ModalBackdrop, ModalViewport
from quantide.web.pages.strategy_routes import (
    _MODAL_MAX_HEIGHTS,
    STRATEGY_MODAL_CLOSE_JS,
)


def _coerce_parameter_text(v):
    """Coerce parameter text."""
    if v.lower() == "true":
        v = True
    elif v.lower() == "false":
        v = False
    else:
        try:
            if "." in v:
                v = float(v)
            else:
                v = int(v)
        except (TypeError, ValueError):
            pass
    return v


def _metric_value_class(value):
    """Metric value class."""
    if value is not None and value > 0:
        value_cls = "text-red-600"
    elif value is not None and value < 0:
        value_cls = "text-green-600"
    else:
        value_cls = "text-gray-700"
    return value_cls


def _strategy_modal_script() -> Any:
    """提供策略页面共用的弹窗打开与关闭脚本。"""
    return Script(src="/static/strategy-modal.js")


def _strategy_dialog_modal(
    title: str,
    body: Any,
    footer: Any,
    *,
    modal_id: str,
    width_cls: str = "max-w-lg",
) -> Any:
    """渲染策略页面统一风格的对话框。

    内容超过黄金分割高度时在正文区域滚动，避免对话框溢出视口。
    """
    max_height_cls = _MODAL_MAX_HEIGHTS.get(width_cls, "max-h-[26rem]")
    return Div(
        ModalBackdrop(),
        Div(
            ModalViewport(
                Div(
                    Div(
                        H3(title, cls="text-lg font-medium leading-6 text-white"),
                        cls="px-6 py-4 bg-[#e41815] shrink-0 rounded-t-lg",
                    ),
                    Div(body, cls="px-6 py-5 overflow-y-auto"),
                    Div(footer, cls="px-6 py-4 border-t border-gray-100 shrink-0"),
                    cls=(
                        "inline-flex flex-col w-full "
                        f"{width_cls} {max_height_cls} overflow-hidden "
                        "rounded-lg bg-white text-left align-middle shadow-xl"
                    ),
                ),
                "flex min-h-full items-center justify-center p-4 text-center",
            ),
            id=modal_id,
        ),
    )


def _normalize_stats(stats):
    """规范化 quantstats 指标名称并返回字典。

    Args:
        stats: quantstats 输出的指标表

    Returns:
        dict: 指标键值对，键为下划线风格
    """
    if stats is None or stats.empty:
        return {}
    series = stats.iloc[:, 0]
    index = series.index.astype(str)
    normalized = index.str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")
    series.index = normalized
    return series.to_dict()


def _to_number(value) -> float | None:
    """将指标值转换为 float。

    Args:
        value: 指标值

    Returns:
        float | None: 数值化结果。百分比字符串会被转换为小数。
    """
    is_percent = False
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "" or cleaned.lower() in {"nan", "n/a", "na"}:
            return None
        is_percent = cleaned.endswith("%")
        if is_percent:
            cleaned = cleaned[:-1].strip()
        value = cleaned
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number / 100 if is_percent else number


def _metric_value(stats_dict: dict[str, Any], *keys: str) -> float | None:
    """解析首个存在的指标值。

    Args:
        stats_dict: 规范化后的指标字典。
        *keys: 候选指标键名，按优先级顺序查找。

    Returns:
        解析后的数值；若所有键都不存在或无法解析，则返回 ``None``。
    """
    for key in keys:
        if key not in stats_dict:
            continue
        value = _to_number(stats_dict[key])
        if value is not None:
            return value
    return None


def _parse_checkbox(value: Any) -> bool:
    """解析 checkbox/form 布尔值。"""
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def _format_date(value) -> str:
    """格式化日期。

    Args:
        value: 日期值

    Returns:
        str: 格式化后的日期文本
    """
    if value is None:
        return "--"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _format_range(start, end) -> str:
    """格式化回测区间。

    Args:
        start: 开始日期
        end: 结束日期

    Returns:
        str: 回测区间文本
    """
    if start is None and end is None:
        return "--"
    return f"{_format_date(start)} ~ {_format_date(end)}"


def _format_percent(value) -> str:
    """格式化百分比值。

    Args:
        value: 百分比数值

    Returns:
        str: 百分比文本
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    return f"{number * 100:.1f}%"


def _format_number(value) -> str:
    """格式化数值。

    Args:
        value: 数值

    Returns:
        str: 格式化后的数字文本
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    return f"{number:.2f}"


def _params_to_text(params: dict) -> str:
    """格式化参数显示文本。

    Args:
        params: 参数字典

    Returns:
        str: 参数文本
    """
    if not params:
        return "--"
    items = []
    for key, value in params.items():
        text_value = value
        if isinstance(value, dict):
            text_value = value.get("default", "")
        elif isinstance(value, (list, tuple, set)):
            text_value = f"{len(value)}项"
        items.append(f"{key}={text_value}")
    return ", ".join(items) if items else "--"


def _foldable_cell(text: str, *, limit: int = 90) -> Any:
    """构建可折叠的文本单元格。

    Args:
        text: 完整文本。
        limit: 摘要保留的字符数。

    Returns:
        Any: 表格单元格节点。
    """
    if not text or len(text) <= limit:
        return Td(text, cls="text-gray-600")
    return Td(
        fh.Details(
            fh.Summary(
                text[:limit] + " …",
                cls="cursor-pointer text-gray-600 hover:text-[#e41815]",
            ),
            Div(
                text,
                cls="text-xs text-gray-700 whitespace-pre-wrap break-all mt-1",
            ),
            cls="text-xs",
        ),
        cls="align-top",
    )


def _extract_params_from_info(info):
    return stored_strategy_config(info)


def _strategy_version(strategy_cls) -> str:
    """获取策略版本。

    Args:
        strategy_cls: 策略类

    Returns:
        str: 版本文本
    """
    if strategy_cls is None:
        return "v1.0.0"
    return getattr(strategy_cls, "VERSION", getattr(strategy_cls, "__version__", "v1.0.0"))


def _get_strategy_default_params(strategy_cls: Any) -> dict[str, Any]:
    """获取策略默认参数字典，兼容 PARAMS 属性与 default_config() 方法。"""
    if strategy_cls is None:
        return {}
    params = getattr(strategy_cls, "PARAMS", None)
    if isinstance(params, dict):
        return dict(params)
    default_config_fn = getattr(strategy_cls, "default_config", None)
    if callable(default_config_fn):
        try:
            cfg = default_config_fn()
            if isinstance(cfg, dict):
                return dict(cfg)
        except Exception:
            pass
    return {}


def _supports_stock_selection(strategy_cls: Any) -> bool:
    """检查策略类是否支持个股筛选接口 select_stocks。"""
    if strategy_cls is None:
        return False
    return callable(getattr(strategy_cls, "select_stocks", None))


def _format_signed_pct(value: Any) -> tuple[str, str]:
    """格式化带正负号的涨跌幅文本及 A 股红涨绿跌样式。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "--", "text-gray-500"
    cls = "text-red-600 font-medium" if num >= 0 else "text-green-600 font-medium"
    return f"{num:+.2%}", cls


def _format_score(value: Any) -> str:
    """格式化机器学习打分 (3 位小数)。"""
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "--"


def _htmx_indicator_style() -> Any:
    """提供 htmx 请求进行中的 loading 指示器样式。"""
    return Style(
        ".htmx-indicator{display:none !important;opacity:1 !important}"
        ".htmx-request.htmx-indicator,"
        ".htmx-request .htmx-indicator{display:flex !important;opacity:1 !important}"
    )


def _global_loading_overlay() -> Any:
    """页面级请求进行中提示（右下角浮层）。"""
    return Div(
        Span(
            cls=(
                "inline-block h-4 w-4 animate-spin rounded-full "
                "border-2 border-white border-t-transparent"
            )
        ),
        Span("正在打开，请稍候…"),
        id="global-loading",
        cls=(
            "htmx-indicator fixed bottom-5 right-5 z-[70] items-center gap-2 "
            "rounded-lg bg-gray-900/90 px-4 py-2.5 text-xs text-white shadow-xl"
        ),
    )


def _coerce_form_value(raw: Any) -> Any:
    """把 form 字符串值转回原始类型 (int / float / bool / str)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return ""
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def strategy_close_button(label="关闭", **attrs):
    return Button(
        label, type="button", cls="btn btn-ghost", onclick=STRATEGY_MODAL_CLOSE_JS, **attrs
    )


def strategy_close_footer():
    return Div(strategy_close_button(), cls="flex justify-end gap-2")
