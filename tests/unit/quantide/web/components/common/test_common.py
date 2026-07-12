"""FR-0502 common web component contract tests.

AC-FR-0502-1 through AC-FR-0502-4: navigation, alert state, parameter
validation, and asset-name fallback stay observable at their public boundary.
"""

import pytest

from quantide.web.components.asset_label import resolve_asset_name
from quantide.web.components.header import header_component
from quantide.web.components.runtime_params import (
    RuntimeParams,
    RuntimeParamsError,
    validate_runtime_params,
)
from quantide.web.components.sidebar import sidebar_component
from quantide.web.components.toast import ToastLevel, auto_dismiss_seconds, requires_aria_alert_role


def _html(node: object) -> str:
    return node.__html__()  # type: ignore[attr-defined]


def test_header_shows_active_navigation_unread_alert_and_user_menu() -> None:
    """FR-0502 AC-1: header exposes active navigation, alert count, and ARIA menu controls."""
    html = _html(
        header_component(
            logo="/logo.svg",
            brand="Quantide",
            nav_items=[("首页", "/"), ("策略", "/strategies")],
            active_title="策略",
            unread_count=2,
            user="devon",
            recent_risk_events=[{"title": "风控告警", "message": "已拦截", "created_at": "10:00"}],
        )
    )

    assert "策略" in html
    assert "border-primary text-primary" in html
    assert ">2<" in html
    assert "风控告警" in html
    assert 'aria-haspopup="menu"' in html


def test_sidebar_fragment_navigation_is_opt_in_and_keeps_active_child() -> None:
    """FR-0502 AC-2: enabled HTMX navigation targets the layout and preserves active child state."""
    html = _html(
        sidebar_component(
            [{"title": "交易", "children": [{"title": "订单", "url": "/orders", "active": True}]}],
            enable_fragment_navigation=True,
        )
    )

    assert 'hx-target="#layout-main-content"' in html
    assert 'hx-push-url="true"' in html
    assert "订单" in html
    assert "text-[#e41815]" in html


@pytest.mark.parametrize(
    ("level", "seconds", "is_alert"),
    [
        (ToastLevel.SUCCESS, 3, False),
        (ToastLevel.ERROR, None, True),
        (ToastLevel.WARNING, None, False),
        (ToastLevel.INFO, 5, False),
    ],
)
def test_toast_levels_keep_dismissal_and_aria_rules(level: ToastLevel, seconds: int | None, is_alert: bool) -> None:
    """FR-0502 AC-3: each toast level has its specified duration and error ARIA role."""
    assert auto_dismiss_seconds(level) == seconds
    assert requires_aria_alert_role(level) is is_alert


def test_runtime_parameter_boundaries_and_asset_name_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-0502 AC-4: valid parameters pass, invalid ones fail, and missing assets retain their code."""
    assert validate_runtime_params(RuntimeParams(100_000, 0.1, 0.01, 0.01, 0)) is True
    with pytest.raises(RuntimeParamsError, match="滑点"):
        validate_runtime_params(RuntimeParams(100_000, 0.1001))

    monkeypatch.setattr(
        "quantide.web.components.asset_label.stock_list.get_name",
        lambda asset: (_ for _ in ()).throw(KeyError(asset)),
    )
    assert resolve_asset_name("UNKNOWN") == "UNKNOWN"
