"""系统维护 - 运行时监控页面测试。"""

from fasthtml.common import to_xml

from quantide.web.pages.system import runtime_monitor as runtime_monitor_page
from quantide.web.pages.system import runtime_support


def test_runtime_monitor_card_polls_only_when_page_is_active(monkeypatch):
    """运行时监控卡片应在页面可见时轮询刷新。"""
    monkeypatch.setattr(
        runtime_support.strategy_runtime_manager,
        "list_runtime_rows",
        lambda: [
            {
                "mode": "live",
                "runtime_id": "runtime-1",
                "portfolio_id": "paper-1",
                "strategy_name": "demo",
                "strategy_id": "runtime-1",
                "status": "idle",
                "total": 100000.0,
                "positions": 0,
                "orders": 0,
                "updated_at": "2026-04-01 12:00:00",
                "can_start": True,
                "can_stop": False,
            }
        ],
    )

    html = to_xml(
        runtime_support.build_runtime_table_card(
            refresh_path="/system/runtime-monitor/table",
            action_base_path="/system/runtime-monitor",
            target_selector="#runtime-monitor",
        )
    )

    assert 'hx-get="/system/runtime-monitor/table"' in html
    assert "document.visibilityState === 'visible'" in html
    assert "document.hasFocus()" in html
    assert 'hx-swap="innerHTML"' in html
    assert 'hx-post="/system/runtime-monitor/start"' in html
    assert 'hx-target="#runtime-monitor"' in html


def test_runtime_monitor_table_route_returns_refresh_content_without_rebinding_poll(monkeypatch):
    """运行时刷新路由应只返回内容片段。"""
    monkeypatch.setattr(runtime_support.strategy_runtime_manager, "list_runtime_rows", lambda: [])

    html = to_xml(runtime_monitor_page.table(None))

    assert 'id="runtime-monitor"' not in html
    assert 'hx-get="/system/runtime-monitor/table"' not in html
    assert "运行时监控" in html
    assert "暂无运行时实例" in html


def test_runtime_monitor_page_has_content(monkeypatch):
    """完整页面应渲染运行时监控卡片。"""
    monkeypatch.setattr(runtime_support.strategy_runtime_manager, "list_runtime_rows", lambda: [])

    html = to_xml(runtime_monitor_page.index(None, {"auth": "admin"}))

    assert "运行时监控" in html
    assert 'id="runtime-monitor"' in html
    assert 'hx-get="/system/runtime-monitor/table"' in html


def test_app_factory_mounts_runtime_monitor_route():
    """应用工厂应挂载运行时监控路由。"""
    from quantide.app_factory import create_app

    app = create_app(enforce_single_instance=False)
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/system/runtime-monitor" in paths
