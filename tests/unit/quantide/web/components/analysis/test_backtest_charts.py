"""FR-0370 核心图表单元测试.

覆盖 acceptance.md AC-FR0370-1~2:
- 回测报告"概览"页签加载时, 净值曲线 / 回撤图 / 月度收益热力图 均渲染成功
- 月度收益热力图: x 轴年份, y 轴月份; 单元格颜色对应收益; hover 显示数值
"""
from __future__ import annotations

import pytest

from quantide.web.components.analysis.backtest_charts import (
    BacktestChartType,
    ChartSpec,
    build_drawdown_chart_spec,
    build_equity_curve_chart_spec,
    build_monthly_heatmap_spec,
    validate_chart_spec_contains_render_target,
)


class TestEquityCurveChart:
    """AC-FR0370-1: 净值曲线组件渲染."""

    def test_spec_contains_render_target(self):
        spec = build_equity_curve_chart_spec(dates=[], values=[], benchmark=[])
        assert validate_chart_spec_contains_render_target(spec) is True

    def test_spec_has_dual_y_axis(self):
        spec = build_equity_curve_chart_spec(
            dates=["2025-01-01", "2025-02-01"],
            values=[100000, 110000],
            benchmark=[100000, 105000],
        )
        assert spec.x_axis == "date"
        assert "策略净值" in spec.y_axes
        assert "沪深 300" in spec.y_axes


class TestDrawdownChart:
    """AC-FR0370-1: 回撤图组件渲染."""

    def test_spec_contains_render_target(self):
        spec = build_drawdown_chart_spec(dates=[], values=[])
        assert validate_chart_spec_contains_render_target(spec) is True

    def test_y_axis_is_drawdown(self):
        spec = build_drawdown_chart_spec(dates=["2025-01-01"], values=[-0.05])
        assert "回撤" in spec.y_axes


class TestMonthlyHeatmap:
    """AC-FR0370-2: 月度收益热力图."""

    def test_spec_contains_render_target(self):
        spec = build_monthly_heatmap_spec(years=[], months=[], returns=[])
        assert validate_chart_spec_contains_render_target(spec) is True

    def test_axes_are_year_and_month(self):
        spec = build_monthly_heatmap_spec(
            years=[2025], months=[1, 2], returns=[[0.01, -0.02]]
        )
        assert spec.x_axis == "year"
        assert spec.y_axis == "month"

    def test_cells_include_return_value(self):
        spec = build_monthly_heatmap_spec(
            years=[2025], months=[1], returns=[[0.03]]
        )
        assert len(spec.cells) == 1
        assert spec.cells[0].value == 0.03

    def test_positive_return_color_differs_from_negative(self):
        spec = build_monthly_heatmap_spec(
            years=[2025], months=[1, 2], returns=[[0.03, -0.02]]
        )
        colors = {cell.color for cell in spec.cells}
        assert len(colors) == 2


class TestChartSpecValidation:
    def test_missing_render_target_invalid(self):
        spec = ChartSpec(
            chart_type=BacktestChartType.EQUITY_CURVE,
            render_target="",
            x_axis="date",
            y_axis="",
            y_axes=["净值"],
        )
        assert validate_chart_spec_contains_render_target(spec) is False
