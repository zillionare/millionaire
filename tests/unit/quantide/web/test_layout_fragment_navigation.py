"""系统维护 fragment 导航不能把 header/sidebar 重绘进 main。"""

from __future__ import annotations

from tests.e2e.support.system_settings_session import system_settings_e2e_session


def test_system_accounts_htmx_returns_main_and_oob_sidebar_only():
    with system_settings_e2e_session() as session:
        response = session.client.get(
            "/system/accounts",
            headers={"HX-Request": "true"},
            follow_redirects=True,
        )
    assert response.status_code == 200
    text = response.text
    assert 'id="layout-main-content"' in text
    assert "hx-swap-oob" in text
    assert "<header" not in text.lower()


def test_data_calendar_htmx_returns_main_and_oob_sidebar_only():
    with system_settings_e2e_session() as session:
        response = session.client.get(
            "/data/calendar",
            headers={"HX-Request": "true"},
            follow_redirects=True,
        )
    assert response.status_code == 200
    text = response.text
    assert 'id="layout-main-content"' in text
    assert "<header" not in text.lower()


def test_top_factor_tab_htmx_returns_main_oob_sidebar_header_and_title():
    with system_settings_e2e_session() as session:
        response = session.client.get(
            "/factors/",
            headers={"HX-Request": "true"},
            follow_redirects=True,
        )
    assert response.status_code == 200
    text = response.text
    assert 'id="layout-main-content"' in text
    assert 'id="layout-sidebar"' in text
    assert 'hx-swap-oob="true"' in text
    assert 'id="layout-header"' in text
    assert 'id="page-title"' in text
    assert 'hx-get="/strategy"' in text
    assert 'hx-target="#layout-main-content"' in text
    assert 'hx-select="#layout-main-content"' in text
    assert 'flex flex-col min-h-screen' not in text
    assert "<!doctype" not in text.lower()


def test_top_strategy_tab_htmx_returns_header_oob():
    with system_settings_e2e_session() as session:
        response = session.client.get(
            "/strategy",
            headers={"HX-Request": "true"},
            follow_redirects=True,
        )
    assert response.status_code == 200
    text = response.text
    assert 'id="layout-main-content"' in text
    assert 'id="layout-header"' in text
    assert 'hx-get="/factors"' in text
    assert 'flex flex-col min-h-screen' not in text
    assert "<!doctype" not in text.lower()
