"""An administrator can change listener settings without resetting the profile."""

import pytest
from starlette.websockets import WebSocketDisconnect

from quantide.data.sqlite import db
from quantide.service.init_wizard import init_wizard
from tests.e2e.support.auth_fixture import ensure_test_admin
from tests.e2e.support.system_settings_session import system_settings_e2e_session

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]


def test_network_page_saves_lan_and_port_for_next_restart():
    with system_settings_e2e_session() as session:
        before = init_wizard.get_state(force_refresh=True)
        response = session.client.get('/system/network/', follow_redirects=True)
        assert response.status_code == 200
        assert '只允许本机访问' in response.text
        response = session.client.post('/system/network/save', data={'app_port': '9231'},
                                       follow_redirects=False)
        assert response.status_code == 303
        state = init_wizard.get_state(force_refresh=True)
        assert (state.app_host, state.app_port) == ('0.0.0.0', 9231)
        assert state.app_home == before.app_home and state.tushare_token == before.tushare_token
        response = session.client.post('/system/network/save',
                                       data={'app_port': '0', 'localhost_only': 'true'})
        assert '端口必须介于' in response.text
        state = init_wizard.get_state(force_refresh=True)
        assert (state.app_host, state.app_port) == ('0.0.0.0', 9231)
        session.client.post('/system/network/save', data={'app_port': '8130', 'localhost_only': 'true'})
        assert init_wizard.get_state(force_refresh=True).app_host == '127.0.0.1'


def test_non_admin_cannot_change_listener():
    with system_settings_e2e_session() as session:
        ensure_test_admin(username='viewer', password='viewer123', email='viewer@example.com', role='user')
        session.client.post('/auth/login', data={'username': 'viewer', 'password': 'viewer123'})
        response = session.client.post('/system/network/save', data={'app_port': '9231'})
        assert response.status_code == 403
        response = session.client.post('/init-wizard/step/2?force=true', data={'nav': 'next'})
        assert response.status_code == 403
        assert init_wizard.get_state(force_refresh=True).app_port == 8130


def test_builtin_strategies_appear_without_manual_scan():
    with system_settings_e2e_session() as session:
        db.execute('DELETE FROM strategy_info')
        db.conn.commit()
        response = session.client.get('/strategy/', follow_redirects=True)
        assert response.status_code == 200
        assert 'DualMAStrategy' in response.text
        assert '内置示例已自动加载' in response.text
        assert db['strategy_info'].count > 0


def test_logged_out_user_cannot_access_mounted_pages_or_force_reconfigure():
    with system_settings_e2e_session() as session:
        session.client.cookies.clear()
        for path in ('/strategy/', '/system/accounts/', '/system/datasource/', '/broker/status'):
            response = session.client.get(path, follow_redirects=False)
            assert response.status_code == 303
            assert response.headers['location'] == '/auth/login'
        response = session.client.post('/init-wizard/step/2?force=true', data={'nav': 'next'},
                                       follow_redirects=False)
        assert response.status_code == 401
        assert session.client.get('/api/health').status_code == 200
        with pytest.raises(WebSocketDisconnect):
            with session.client.websocket_connect('/strategy/backtest/test/ws') as websocket:
                websocket.receive_json()
