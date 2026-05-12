"""系统维护 - 风险事件中心页面测试。"""

from fasthtml.common import to_xml

from quantide.web.pages.system import risk_events as risk_events_page
from quantide.web.pages.system import runtime_support


def test_risk_event_center_card_refreshes_only_when_page_is_active(monkeypatch):
    """风险事件卡片应在页面可见时轮询刷新。"""
    monkeypatch.setattr(
        runtime_support.strategy_runtime_manager,
        "risk_summary",
        lambda: {
            "blocked_accounts": 1,
            "blocked_strategies": 1,
            "open_events": 2,
            "event_count": 2,
        },
    )
    monkeypatch.setattr(
        runtime_support.strategy_runtime_manager,
        "list_risk_events",
        lambda limit=8: [
            {
                "severity": "critical",
                "title": "账户已封锁",
                "message": "账户 live:gateway 已被封锁",
                "scope": "account",
                "created_at": "2026-05-08T12:00:00",
            }
        ],
    )

    html = to_xml(runtime_support.build_risk_event_center_card("/system/risk-events/panel"))

    assert 'hx-get="/system/risk-events/panel"' in html
    assert "document.visibilityState === 'visible'" in html
    assert "document.hasFocus()" in html
    assert 'hx-swap="innerHTML"' in html
    assert "账户已封锁" in html


def test_risk_event_panel_route_returns_refresh_content_without_rebinding_poll(monkeypatch):
    """风险事件刷新路由应只返回内容片段。"""
    monkeypatch.setattr(
        runtime_support.strategy_runtime_manager,
        "risk_summary",
        lambda: {
            "blocked_accounts": 0,
            "blocked_strategies": 0,
            "open_events": 0,
            "event_count": 0,
        },
    )
    monkeypatch.setattr(runtime_support.strategy_runtime_manager, "list_risk_events", lambda limit=8: [])

    html = to_xml(risk_events_page.panel(None))

    assert 'id="risk-event-center"' not in html
    assert 'hx-get="/system/risk-events/panel"' not in html
    assert "风险事件中心" in html
    assert "暂无风险事件" in html


def test_risk_events_page_has_content(monkeypatch):
    """完整页面应渲染风险事件中心卡片。"""
    monkeypatch.setattr(
        runtime_support.strategy_runtime_manager,
        "risk_summary",
        lambda: {
            "blocked_accounts": 0,
            "blocked_strategies": 0,
            "open_events": 0,
            "event_count": 0,
        },
    )
    monkeypatch.setattr(runtime_support.strategy_runtime_manager, "list_risk_events", lambda limit=8: [])

    html = to_xml(risk_events_page.index(None, {"auth": "admin"}))

    assert "风险事件中心" in html
    assert 'id="risk-event-center"' in html
    assert 'hx-get="/system/risk-events/panel"' in html


def test_app_factory_mounts_risk_events_route():
    """应用工厂应挂载风险事件中心路由。"""
    from quantide.app_factory import create_app

    app = create_app(enforce_single_instance=False)
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/system/risk-events" in paths
