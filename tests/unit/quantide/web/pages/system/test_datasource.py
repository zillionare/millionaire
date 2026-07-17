"""系统设置 - 数据源页面测试"""

from unittest.mock import MagicMock, PropertyMock, patch

from starlette.testclient import TestClient

import pytest


@pytest.fixture(scope="module")
def client():
    """创建测试客户端"""
    from quantide.app_factory import create_app

    app = create_app(enforce_single_instance=False)
    with TestClient(app) as c:
        yield c


class TestDatasourcePage:
    """数据源页面测试"""

    def test_datasource_page_ok(self, client):
        """页面返回 200"""
        resp = client.get("/system/datasource/", follow_redirects=True)
        assert resp.status_code == 200

    def test_datasource_redirect(self, client):
        """不带尾部斜杠时 303 重定向"""
        resp = client.get("/system/datasource", follow_redirects=False)
        assert resp.status_code == 303
        assert "/system/datasource/" in resp.headers["location"]

    def test_datasource_has_layout(self, client):
        """页面包含布局元素（header, sidebar）"""
        resp = client.get("/system/datasource/", follow_redirects=True)
        assert "<nav" in resp.text.lower()
        assert "<aside" in resp.text.lower()

    def test_datasource_has_content(self, client):
        """页面包含数据源内容"""
        resp = client.get("/system/datasource/", follow_redirects=True)
        assert "数据源" in resp.text
        assert "Tushare" in resp.text

    def test_datasource_has_data_status(self, client):
        """页面包含数据状态"""
        resp = client.get("/system/datasource/", follow_redirects=True)
        assert "数据状态" in resp.text or "日线数据" in resp.text

    def test_datasource_has_sync_button(self, client):
        """页面包含手动同步按钮"""
        resp = client.get("/system/datasource/", follow_redirects=True)
        assert "同步" in resp.text


class TestDatasourceSync:
    """数据源同步功能测试"""

    def test_datasource_sync_page(self, client, monkeypatch):
        """同步页面可访问"""
        from quantide.data.models.calendar import calendar as trade_calendar
        from quantide.data.models.daily_bars import daily_bars
        from quantide.data.models.stocks import stock_list

        monkeypatch.setattr(trade_calendar, "update", lambda: None)
        monkeypatch.setattr(stock_list, "update", lambda: None)

        with patch.object(
            type(daily_bars),
            "store",
            new_callable=PropertyMock,
            return_value=MagicMock(),
        ):
            resp = client.get("/system/datasource/sync", follow_redirects=True)
        assert resp.status_code == 200
        # 应该显示同步结果
        assert "同步" in resp.text
