"""系统维护 - 股票列表页面测试"""

import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """创建测试客户端"""
    from quantide.app_factory import create_app
    from tests.e2e.support.auth_fixture import sign_in_test_admin

    app = create_app(enforce_single_instance=False)
    with TestClient(app) as c:
        sign_in_test_admin(c)
        yield c


class TestStocksPage:
    """股票列表页面测试"""

    def test_stocks_page_ok(self, client):
        """页面返回 200"""
        resp = client.get("/system/stocks/", follow_redirects=True)
        assert resp.status_code == 200

    def test_stocks_redirect(self, client):
        """不带尾部斜杠时 303 重定向"""
        resp = client.get("/system/stocks", follow_redirects=False)
        assert resp.status_code == 303
        assert "/system/stocks/" in resp.headers["location"]

    def test_stocks_has_layout(self, client):
        """页面包含布局元素"""
        resp = client.get("/system/stocks/", follow_redirects=True)
        assert "<nav" in resp.text.lower()
        assert "<aside" in resp.text.lower()

    def test_stocks_no_search_button(self, client):
        """不应有搜索按钮"""
        resp = client.get("/system/stocks/", follow_redirects=True)
        # placeholder 中的"搜索"不算，只检查 submit 类型的按钮
        assert "搜索</button>" not in resp.text

    def test_stocks_has_debounce(self, client):
        """输入框配置了 200ms 防抖"""
        resp = client.get("/system/stocks/", follow_redirects=True)
        assert "delay:200ms" in resp.text

    def test_stocks_search_input_uses_full_width(self, client):
        """搜索框使用整行宽度，不再限制为 max-w-md。"""
        resp = client.get("/system/stocks/", follow_redirects=True)
        assert 'name="q"' in resp.text
        assert "input input-bordered w-full" in resp.text

    def test_stocks_update_is_header_icon_button(self, client):
        """立即更新按钮改为标题栏右侧图标按钮。"""
        resp = client.get("/system/stocks/", follow_redirects=True)
        assert 'hx-post="/system/stocks/sync"' in resp.text
        assert 'title="立即更新"' in resp.text
        assert "立即更新</button>" not in resp.text
        assert "inline-flex h-5 w-5" in resp.text
        assert "uk-btn" not in resp.text

    def test_search_api_digits(self, client):
        """搜索 API - 全数字匹配代码开头"""
        resp = client.get("/system/stocks/search?q=000", follow_redirects=True)
        assert resp.status_code == 200
        assert "000001.SZ" in resp.text

    def test_search_api_chinese(self, client):
        """搜索 API - 汉字匹配名称"""
        resp = client.get("/system/stocks/search?q=%E5%B9%B3%E5%AE%89", follow_redirects=True)
        assert resp.status_code == 200
        assert "平安银行" in resp.text

    def test_search_api_pinyin(self, client):
        """搜索 API - 拼音匹配"""
        resp = client.get("/system/stocks/search?q=payh", follow_redirects=True)
        assert resp.status_code == 200
        assert "平安银行" in resp.text

    def test_search_api_empty(self, client):
        """搜索 API - 空查询返回全部"""
        resp = client.get("/system/stocks/search?q=", follow_redirects=True)
        assert resp.status_code == 200
