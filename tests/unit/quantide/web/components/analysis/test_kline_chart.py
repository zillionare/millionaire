"""FR-0501 analysis KlineChart contract tests.

AC-FR-0501-1 and AC-FR-0501-2: chart output preserves its target,
rendering scripts, controls, and selection state.
"""

from quantide.web.components.analysis.kline_chart import KlineChart


def _html(node: object) -> str:
    return node.__html__()  # type: ignore[attr-defined]


def test_render_includes_chart_target_and_update_script() -> None:
    """FR-0501 AC-1: populated charts expose an isolated target and update script."""
    html = _html(KlineChart(chart_id="daily-chart", height=320, symbol="000001", name="平安银行").render())

    assert 'id="daily-chart"' in html
    assert "平安银行 (000001)" in html
    assert "height: 320px" in html
    assert "updateKlineData_daily_chart" in html


def test_render_empty_chart_keeps_stable_container() -> None:
    """FR-0501 AC-1: an empty chart renders a stable selectable container."""
    html = _html(KlineChart(chart_id="empty-chart").render())

    assert 'id="empty-chart"' in html
    assert "请选择股票" in html


def test_frequency_and_ma_controls_target_only_their_chart() -> None:
    """FR-0501 AC-2: controls retain actions and the selected frequency per chart."""
    freq_html = _html(KlineChart.freq_buttons("weekly-chart", current_freq="week"))
    ma_html = _html(KlineChart.ma_buttons("weekly-chart", ma_periods=[5, 20]))

    assert "switchFreq_weekly_chart('week')" in freq_html
    assert "bg-blue-600 text-white" in freq_html
    assert "switchFreq_weekly_chart('day')" in freq_html
    assert "toggleMA_weekly_chart(5)" in ma_html
    assert "toggleMA_weekly_chart(20)" in ma_html
