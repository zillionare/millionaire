"""Web rendering contracts for five-state wind-tunnel badges."""

from __future__ import annotations

from fasthtml.common import Div

from quantide.factors.metadata import FACTOR_METADATA
from quantide.service.factor_audit import WindTunnelBadgeView
from quantide.service.factor_tracking import TrackingView, default_profile


def _view(
    status: str,
    *,
    target_id: str = "bias_5",
    kind: str = "factor",
    message: str = "",
) -> WindTunnelBadgeView:
    return WindTunnelBadgeView(
        target_kind=kind,  # type: ignore[arg-type]
        target_id=target_id,
        badge_status=status,  # type: ignore[arg-type]
        run_id="run-1",
        checked_at="2026-01-01T15:00:00",
        source_hash="source",
        recorded_source_hash="source",
        data_hash="data",
        recorded_data_hash="data",
        config_hash="config",
        recorded_config_hash="config",
        check_items=(
            {"id": "future", "required": True, "status": status, "message": message},
        ),
        first_difference_summary="2025-01-01 · 000001.SZ：期望 1，实际 2",
        message=message,
    )


def test_badge_renders_all_five_states() -> None:
    from quantide.web.pages.wind_tunnel_ui import wind_tunnel_badge, wind_tunnel_card

    for status in ("PASS", "FAIL", "INCONCLUSIVE", "STALE", "UNVERIFIED"):
        html = str(Div(wind_tunnel_badge(_view(status))))
        assert status in html
        card = str(Div(wind_tunnel_card(_view(status), run_url="/run", export_url="/export")))
        assert "风洞体检详情" in card
        assert "source" in card


def test_factor_overview_marks_failed_factor_as_risk_block() -> None:
    from quantide.web.pages import factors_overview

    assert factors_overview.factor_wind_tunnel_badge is not None
    original = factors_overview.factor_wind_tunnel_badge
    factors_overview.factor_wind_tunnel_badge = lambda factor_id: _view(
        "FAIL", target_id=factor_id
    )
    try:
        view = TrackingView(
            profile=default_profile("bias_5"),
            current=None,
            last_attempt=None,
            status="pending",
        )
        html = str(factors_overview.overview_row(FACTOR_METADATA["bias_5"], view))
    finally:
        factors_overview.factor_wind_tunnel_badge = original

    assert "风洞 FAIL" in html
    assert "默认阻断新建回测" in html


def test_backtest_wizard_disables_failed_factor_checkbox() -> None:
    from quantide.web.pages import strategy_backtest_views

    original = strategy_backtest_views.factor_wind_tunnel_badge
    strategy_backtest_views.factor_wind_tunnel_badge = lambda factor_id: _view(
        "FAIL" if factor_id == "bias_5" else "PASS", target_id=factor_id
    )
    try:
        html = str(strategy_backtest_views._build_feature_selection_panel())
    finally:
        strategy_backtest_views.factor_wind_tunnel_badge = original

    assert "风洞 FAIL 已阻断" in html
    assert "disabled" in html
