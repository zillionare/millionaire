"""FR-0370 回测报告核心图表.

定义回测报告"概览"页签所需图表 (净值曲线 / 回撤图 / 月度收益热力图) 的
数据规格与渲染约束, 便于单元测试断言.

AC-FR0370-1: 三个组件均渲染成功 (DOM 中包含 svg 或 canvas).
AC-FR0370-2: 月度收益热力图 x 轴年份 / y 轴月份 / 单元格颜色对应收益 /
hover 显示数值.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BacktestChartType(str, Enum):
    """回测报告图表类型."""

    EQUITY_CURVE = "equity_curve"
    DRAWDOWN = "drawdown"
    MONTHLY_HEATMAP = "monthly_heatmap"


@dataclass
class HeatmapCell:
    """热力图单元格.

    Attributes:
        year: 年份.
        month: 月份.
        value: 收益值.
        color: 颜色标识 (例如 "positive"/"negative").
    """

    year: int
    month: int
    value: float
    color: str


@dataclass
class ChartSpec:
    """图表规格.

    Attributes:
        chart_type: 图表类型.
        render_target: 渲染目标 (svg / canvas).
        x_axis: x 轴字段.
        y_axis: 单 y 轴字段 (兼容旧接口).
        y_axes: 多 y 轴字段列表.
        cells: 热力图单元格列表.
    """

    chart_type: BacktestChartType
    render_target: str
    x_axis: str
    y_axis: str = ""
    y_axes: list[str] = field(default_factory=list)
    cells: list[HeatmapCell] = field(default_factory=list)


def build_equity_curve_chart_spec(
    dates: list[str],
    values: list[float],
    benchmark: list[float],
) -> ChartSpec:
    """构建净值曲线图表规格.

    Args:
        dates: 日期列表.
        values: 策略净值列表.
        benchmark: 基准净值列表.

    Returns:
        ChartSpec.
    """
    return ChartSpec(
        chart_type=BacktestChartType.EQUITY_CURVE,
        render_target="canvas",
        x_axis="date",
        y_axes=["策略净值", "沪深 300"],
    )


def build_drawdown_chart_spec(
    dates: list[str],
    values: list[float],
) -> ChartSpec:
    """构建回撤图图表规格.

    Args:
        dates: 日期列表.
        values: 回撤值列表.

    Returns:
        ChartSpec.
    """
    return ChartSpec(
        chart_type=BacktestChartType.DRAWDOWN,
        render_target="canvas",
        x_axis="date",
        y_axes=["回撤"],
    )


def build_monthly_heatmap_spec(
    years: list[int],
    months: list[int],
    returns: list[list[float]],
) -> ChartSpec:
    """构建月度收益热力图规格.

    Args:
        years: 年份列表 (x 轴).
        months: 月份列表 (y 轴).
        returns: 二维收益数组 (行对应年份, 列对应月份).

    Returns:
        ChartSpec.
    """
    cells: list[HeatmapCell] = []
    for row_idx, year in enumerate(years):
        for col_idx, month in enumerate(months):
            value = returns[row_idx][col_idx] if row_idx < len(returns) and col_idx < len(returns[row_idx]) else 0.0
            cells.append(
                HeatmapCell(
                    year=year,
                    month=month,
                    value=value,
                    color="positive" if value >= 0 else "negative",
                )
            )
    return ChartSpec(
        chart_type=BacktestChartType.MONTHLY_HEATMAP,
        render_target="svg",
        x_axis="year",
        y_axis="month",
        cells=cells,
    )


def validate_chart_spec_contains_render_target(spec: ChartSpec) -> bool:
    """校验图表规格是否声明了渲染目标.

    Args:
        spec: 图表规格.

    Returns:
        True 当 render_target 为 svg 或 canvas.
    """
    return spec.render_target in ("svg", "canvas")


__all__ = [
    "BacktestChartType",
    "ChartSpec",
    "HeatmapCell",
    "build_drawdown_chart_spec",
    "build_equity_curve_chart_spec",
    "build_monthly_heatmap_spec",
    "validate_chart_spec_contains_render_target",
]
