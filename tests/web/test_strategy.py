from fasthtml.common import to_xml

from quantide.web.pages import strategy as strategy_page


def test_runtime_monitor_polls_only_when_page_is_active(monkeypatch):
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
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

    html = to_xml(strategy_page._runtime_table_card())

    assert 'hx-get="/strategy/runtime/table"' in html
    assert "load, every 5s" not in html
    assert "document.visibilityState === 'visible'" in html
    assert "document.hasFocus()" in html
    assert 'hx-swap="innerHTML"' in html
    assert 'hx-post="/strategy/runtime/start"' in html
    assert 'hx-target="#runtime-ops-panel"' in html


def test_runtime_table_route_returns_refresh_content_without_rebinding_poll(monkeypatch):
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "list_runtime_rows",
        lambda: [],
    )

    html = to_xml(strategy_page.runtime_table(None))

    assert 'id="runtime-monitor"' not in html
    assert 'hx-get="/strategy/runtime/table"' not in html
    assert "运行时监控" in html
    assert "暂无运行时实例" in html


def test_risk_event_center_renders_alerts_and_confirmation_actions(monkeypatch):
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "risk_summary",
        lambda: {
            "blocked_accounts": 1,
            "blocked_strategies": 1,
            "open_events": 2,
            "event_count": 2,
        },
    )
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
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
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "list_runtime_rows",
        lambda: [
            {
                "mode": "live",
                "runtime_id": "live:gateway:demo-1",
                "portfolio_id": "gateway",
                "strategy_name": "demo",
                "strategy_id": "demo-1",
                "status": "blocked",
                "alert_text": "人工确认后可解除",
                "total": 100000.0,
                "positions": 0,
                "orders": 0,
                "updated_at": "2026-05-08 12:00:00",
                "blocked_scope": "strategy",
                "can_stop": False,
                "can_start": False,
                "can_block_account": False,
                "can_unblock_account": False,
                "can_block_strategy": False,
                "can_unblock_strategy": True,
            }
        ],
    )

    html = to_xml(strategy_page._runtime_ops_panel())

    assert 'id="risk-event-center"' in html
    assert 'hx-get="/strategy/risk-center"' in html
    assert "风险事件中心" in html
    assert "账户封控 1" in html
    assert "策略封控 1" in html
    assert 'hx-post="/strategy/runtime/unblock"' in html
    assert 'hx-confirm="确认解除策略风控封锁吗？"' in html
