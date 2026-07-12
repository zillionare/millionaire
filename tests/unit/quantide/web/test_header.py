"""Header 组件测试。"""

from fasthtml.common import to_xml

from quantide.web.components.header import header_component


def test_header_alert_center_renders_badge_and_shortcuts():
    """Header 应渲染告警中心 badge 与快捷入口。"""
    html = to_xml(
        header_component(
            logo="/static/logo.png",
            brand="Millionaire",
            nav_items=[("策略", "/strategy")],
            user="admin",
            unread_count=2,
            risk_summary={
                "blocked_accounts": 1,
                "blocked_strategies": 1,
                "open_events": 2,
                "event_count": 2,
            },
            recent_risk_events=[
                {
                    "title": "账户已封锁",
                    "message": "账户 live:gateway 已被封锁",
                    "created_at": "2026-05-12 12:00:00",
                }
            ],
            runtime_summary={"total": 3, "running": 1, "blocked": 1, "failed": 1, "idle": 0},
        )
    )

    assert 'aria-label="告警中心"' in html
    assert "账户已封锁" in html
    assert "/system/risk-events/" in html
    assert "/system/runtime-monitor/" in html
    assert ">2<" in html


def test_header_alert_center_shows_empty_state_without_open_events():
    """没有告警时 header 应展示空态文案。"""
    html = to_xml(
        header_component(
            logo="/static/logo.png",
            brand="Millionaire",
            nav_items=[("策略", "/strategy")],
            user="admin",
        )
    )

    assert "当前没有待处理风险事件" in html
    assert "告警中心" in html
