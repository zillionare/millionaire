"""系统设置 - 交易网关页面测试。"""

from contextlib import contextmanager

from starlette.testclient import TestClient

import pytest

from tests.e2e.support.system_settings_session import system_settings_e2e_session


@pytest.fixture(scope="module")
def client():
    """创建已初始化且已登录的测试客户端。"""

    @contextmanager
    def _client_context():
        with system_settings_e2e_session() as session:
            yield session.client

    with _client_context() as c:
        yield c


class TestGatewayPage:
    """交易网关页面测试"""

    def test_gateway_page_ok(self, client):
        """页面返回 200"""
        resp = client.get("/system/gateway/", follow_redirects=True)
        assert resp.status_code == 200

    def test_gateway_redirect(self, client):
        """不带尾部斜杠时 303 重定向"""
        resp = client.get("/system/gateway", follow_redirects=False)
        assert resp.status_code == 303
        assert "/system/gateway/" in resp.headers["location"]

    def test_gateway_has_layout(self, client):
        """页面包含布局元素（header, sidebar）"""
        resp = client.get("/system/gateway/", follow_redirects=True)
        assert "<nav" in resp.text.lower()
        assert "<aside" in resp.text.lower()

    def test_gateway_has_content(self, client):
        """页面包含交易网关内容"""
        resp = client.get("/system/gateway/", follow_redirects=True)
        assert "交易网关" in resp.text
        assert "连接状态" in resp.text or "连接配置" in resp.text

    def test_gateway_shows_dev_stub_notice_when_enabled(self, client, monkeypatch):
        """开发 stub 模式下展示 effective gateway 提示。"""

        monkeypatch.setattr("quantide.web.pages.system.gateway.dev_stubs_enabled", lambda: True)
        monkeypatch.setattr(
            "quantide.web.pages.system.gateway.get_settings",
            lambda: type("Settings", (), {"gateway_base_url": "/runtime-gateway"})(),
        )

        resp = client.get("/system/gateway/", follow_redirects=True)

        assert resp.status_code == 200
        assert "开发 Stub 运行时" in resp.text
        assert "当前运行地址：/runtime-gateway。" in resp.text

    def test_gateway_htmx_request_returns_layout_fragment(self, client):
        """HTMX 请求只返回 main fragment 和 sidebar OOB。"""
        resp = client.get(
            "/system/gateway/",
            headers={"HX-Request": "true"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert "交易网关" in resp.text
        assert 'id="layout-main-content"' in resp.text
        assert 'id="layout-sidebar"' in resp.text
        assert 'hx-swap-oob="true"' in resp.text
        assert "<title>" not in resp.text.lower()
        assert "<html" not in resp.text.lower()

    def test_gateway_has_test_button(self, client):
        """页面包含连接测试按钮"""
        resp = client.get("/system/gateway/", follow_redirects=True)
        assert "连接测试" in resp.text


class TestGatewayConnectionTest:
    """交易网关连接测试功能"""

    def test_gateway_test_endpoint(self, client):
        """测试连接端点返回内容"""
        resp = client.get("/system/gateway/test", follow_redirects=True)
        assert resp.status_code == 200
        # 应该返回状态卡片 HTML
        assert "网关" in resp.text or "连接" in resp.text
